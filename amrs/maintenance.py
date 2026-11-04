"""Dry-run-first cleanup, bound to reviewed targets and verified backup evidence."""

import argparse
import getpass
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import db


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def preview():
    target = db.one(
        "SELECT SYS_CONTEXT('USERENV','DB_UNIQUE_NAME') db_name,SYS_CONTEXT('USERENV','CON_NAME') container_name,SYS_CONTEXT('USERENV','CURRENT_SCHEMA') schema_name FROM dual"
    )
    groups = {
        "students": db.rows(
            "SELECT student_id id FROM students WHERE is_active=0 ORDER BY student_id"
        ),
        "courses": db.rows(
            "SELECT course_id id FROM courses WHERE is_active=0 ORDER BY course_id"
        ),
        "teachers": db.rows(
            "SELECT u.user_id id FROM users u JOIN roles r ON r.role_id=u.role_id WHERE u.is_active=0 AND r.role_name='TEACHER' ORDER BY u.user_id"
        ),
    }
    protected = db.one(
        "SELECT COUNT(*) n FROM courses c JOIN users u ON u.user_id=c.teacher_id WHERE c.is_active=1 AND u.is_active=0"
    )["n"]
    return {
        "target": target,
        "counts": {key: len(value) for key, value in groups.items()},
        "targets_sha256": digest(groups),
        "protected_active_courses": protected,
    }


def validate_approval(approval, plan):
    try:
        if (
            approval["plan_sha256"] != digest(plan)
            or approval["approved"] is not True
            or approval["restore_verified"] is not True
            or not approval["approved_by"].strip()
        ):
            raise ValueError()
        stamp = datetime.fromisoformat(approval["approved_at"])
        if stamp.tzinfo is None or not timedelta(0) <= datetime.now(
            UTC
        ) - stamp <= timedelta(days=1):
            raise ValueError()
        for prefix in ("backup", "restore_report"):
            path = Path(approval[prefix + "_file"])
            if not path.is_absolute() or path.stat().st_size == 0:
                raise ValueError()
            checksum = hashlib.sha256()
            with path.open("rb") as handle:
                while data := handle.read(1024 * 1024):
                    checksum.update(data)
            if checksum.hexdigest() != approval[prefix + "_sha256"]:
                raise ValueError()
    except KeyError, TypeError, ValueError, OSError:
        raise ValueError(
            "Cleanup requires a matching reviewed plan, verified backup/restore files and explicit approval less than 24 hours old."
        ) from None


def purge_inactive_records(*, confirm=False, approval=None, user=None):
    plan = preview()
    if not confirm:
        return plan
    from .devices import authorize

    authorize(user)
    if plan["protected_active_courses"]:
        raise ValueError(
            "Reassign active courses belonging to inactive teachers before cleanup."
        )
    validate_approval(approval or {}, plan)
    with db.connection() as connection:
        cur = connection.cursor()
        for table in ("students", "users", "courses"):
            cur.execute("LOCK TABLE " + table + " IN EXCLUSIVE MODE WAIT 5")
        cur.execute("SELECT student_id FROM students WHERE is_active=0")
        student_ids = [row[0] for row in cur]
        cur.execute(
            "SELECT u.user_id FROM users u JOIN roles r ON r.role_id=u.role_id WHERE u.is_active=0 AND r.role_name='TEACHER'"
        )
        teacher_ids = [row[0] for row in cur]
        cur.execute("SELECT course_id FROM courses WHERE is_active=0")
        course_ids = [row[0] for row in cur]
        groups = {
            "students": [{"id": v} for v in sorted(student_ids)],
            "teachers": [{"id": v} for v in sorted(teacher_ids)],
            "courses": [{"id": v} for v in sorted(course_ids)],
        }
        if digest(groups) != plan["targets_sha256"]:
            raise ValueError(
                "Records changed since the approved preview. Generate a new plan."
            )
        cur.execute(
            "SELECT COUNT(*) FROM courses c JOIN users u ON u.user_id=c.teacher_id WHERE c.is_active=1 AND u.is_active=0"
        )
        if cur.fetchone()[0]:
            raise ValueError("Active-course protection changed; cleanup refused.")
        for table in ("email_password_resets", "password_reset_requests"):
            cur.execute(
                "DELETE FROM "
                + table
                + " WHERE user_type='STUDENT' AND user_id IN (SELECT student_id FROM students WHERE is_active=0)"
            )
        cur.execute("DELETE FROM students WHERE is_active=0")
        cur.execute("DELETE FROM courses WHERE is_active=0")
        teacher_sql = "SELECT u.user_id FROM users u JOIN roles r ON r.role_id=u.role_id WHERE u.is_active=0 AND r.role_name='TEACHER'"
        for table in ("attendance", "checkin_sessions"):
            cur.execute(
                "DELETE FROM " + table + " WHERE teacher_id IN (" + teacher_sql + ")"
            )
        for table in ("password_reset_requests", "email_password_resets"):
            cur.execute(
                "DELETE FROM "
                + table
                + " WHERE user_type='TEACHER' AND user_id IN ("
                + teacher_sql
                + ")"
            )
        cur.execute(
            "DELETE FROM teacher_signup_requests WHERE LOWER(email) IN (SELECT LOWER(u.email) FROM users u JOIN roles r ON r.role_id=u.role_id WHERE u.is_active=0 AND r.role_name='TEACHER')"
        )
        cur.execute("DELETE FROM users WHERE user_id IN (" + teacher_sql + ")")
        db.audit_event(
            cur,
            user,
            "INACTIVE_PURGE",
            plan["targets_sha256"][:32],
            json.dumps(plan["counts"]),
        )
    failed = delete_face_photos(student_ids)
    return dict(plan, executed=True, biometric_cleanup_failures=len(failed))


def delete_face_photos(student_ids):
    from . import face

    failed = []
    for sid in student_ids:
        face.safe_student_id(sid)
        for directory, suffix in (
            (face.FACE_DIR, ".template"),
            (face.FACE_DIR, ".image"),
            (face.LEGACY_FACE_DIR, ".png"),
        ):
            path = directory / (sid + suffix)
            try:
                if path.resolve().parent != directory.resolve():
                    raise ValueError("Invalid face path")
                path.unlink(missing_ok=True)
            except OSError, ValueError:
                failed.append(sid)
    return failed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--admin-email")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    if args.confirm and (not args.approval or not args.admin_email):
        parser.error("--confirm requires --approval and --admin-email")
    from .configuration import load_runtime

    if not load_runtime():
        parser.error(
            "Configure the Oracle runtime connection in the desktop application first."
        )
    user = (
        db.login("ADMIN", args.admin_email, getpass.getpass("Administrator password: "))
        if args.confirm
        else None
    )
    approval = json.loads(args.approval.read_text()) if args.approval else None
    result = purge_inactive_records(confirm=args.confirm, approval=approval, user=user)
    if not args.confirm:
        result["plan_sha256"] = digest(result)
    text = json.dumps(result, indent=2)
    print(text)
    if args.report:
        with args.report.open("x", encoding="utf-8") as handle:
            handle.write(text)
    return 0
