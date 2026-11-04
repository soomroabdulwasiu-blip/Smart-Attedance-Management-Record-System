"""Prefetch initial presentation reads away from Qt's UI thread."""

from . import db


def prefetch(user):
    with db.capture_reads() as snapshot:
        db.departments()
        db.courses(user)
        db.attendance(user)
        db.student_profile(user) if user["role"] == "STUDENT" else None
        if user["role"] == "ADMIN":
            db.students()
            db.teachers()
            db.courses()
            db.one("SELECT COUNT(*) n FROM attendance")
            db.pending_resets()
            db.pending_teacher_signups(user)
        elif user["role"] == "TEACHER":
            db.teacher_dashboard_stats(user["user_id"])
        else:
            db.student_summary(user["user_id"])
        if user["role"] in ("TEACHER", "STUDENT"):
            db.correction_requests(user)
    return snapshot


def authenticate(role, identity, password):
    user = db.login(role, identity, password)
    user["_initial_reads"] = prefetch(user)
    return user
