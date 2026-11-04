"""Class/section assignment and institution settings, with Oracle transactions."""

import json

from . import db
from .devices import authorize

DEFAULT_POLICY = {"minimum_percent": 75, "editing_days": 3, "late_counts_present": True}


def classes(user):
    authorize(user, ("ADMIN", "TEACHER", "STUDENT"))
    restriction, params = "", {}
    if user["role"] == "TEACHER":
        restriction = " AND EXISTS (SELECT 1 FROM courses c WHERE c.class_id=a.class_id AND c.teacher_id=:actor AND c.is_active=1)"
        params["actor"] = user["user_id"]
    elif user["role"] == "STUDENT":
        restriction = " AND EXISTS (SELECT 1 FROM courses c JOIN course_enrollments e ON e.course_id=c.course_id WHERE c.class_id=a.class_id AND e.student_id=:actor AND c.is_active=1)"
        params["actor"] = user["user_id"]
    return db.rows(
        "SELECT a.*,d.dept_name FROM academic_classes a JOIN departments d ON d.dept_id=a.dept_id WHERE a.is_active=1"
        + restriction
        + " ORDER BY academic_year DESC,class_name,section_name",
        params,
    )


def save_class(user, name, dept_id, semester, section, year, class_id=None):
    authorize(user)
    name, section = name.strip(), section.strip().upper()
    if (
        not 1 <= len(name) <= 120
        or not 1 <= len(section) <= 40
        or not 1 <= semester <= 16
        or not 1990 <= year <= 2200
    ):
        raise ValueError(
            "Enter a class name, section, semester and valid academic year."
        )
    class_id = class_id or db.uid()
    with db.connection() as connection:
        cur = connection.cursor()
        cur.execute(
            "MERGE INTO academic_classes a USING (SELECT :id class_id FROM dual) x ON(a.class_id=x.class_id) WHEN MATCHED THEN UPDATE SET class_name=:name,dept_id=:dept,semester=:sem,section_name=:section,academic_year=:year WHEN NOT MATCHED THEN INSERT(class_id,class_name,dept_id,semester,section_name,academic_year) VALUES(:id,:name,:dept,:sem,:section,:year)",
            {
                "id": class_id,
                "name": name,
                "dept": dept_id,
                "sem": semester,
                "section": section,
                "year": year,
            },
        )
        db.audit_event(cur, user, "CLASS_SAVED", class_id)
    return class_id


def assign_course(user, class_id, course_id):
    authorize(user)
    with db.connection() as connection:
        cur = connection.cursor()
        cur.execute(
            "UPDATE courses c SET class_id=:class_id WHERE course_id=:course AND is_active=1 AND EXISTS (SELECT 1 FROM academic_classes a WHERE a.class_id=:class_id AND a.is_active=1 AND a.dept_id=c.dept_id AND a.semester=c.semester)",
            {"class_id": class_id, "course": course_id},
        )
        if cur.rowcount != 1:
            raise ValueError(
                "Class and course must have the same department and semester."
            )
        db.audit_event(cur, user, "COURSE_CLASS_ASSIGNED", course_id)


def delete_class(user, class_id):
    authorize(user)
    with db.connection() as connection:
        cur = connection.cursor()
        cur.execute(
            "UPDATE courses SET class_id=NULL WHERE class_id=:id", {"id": class_id}
        )
        cur.execute("DELETE FROM academic_classes WHERE class_id=:id", {"id": class_id})
        if cur.rowcount != 1:
            raise ValueError("Class no longer exists.")
        db.audit_event(
            cur,
            user,
            "CLASS_REMOVED",
            class_id,
            "Course enrollments and attendance preserved",
        )


def get_policy(user):
    authorize(user, ("ADMIN", "TEACHER", "STUDENT"))
    row = db.one(
        "SELECT value_json FROM attendance_settings WHERE setting_key='ATTENDANCE_POLICY'"
    )
    return validate_policy(json.loads(row["value_json"]) if row else DEFAULT_POLICY)


def validate_policy(values):
    if set(values) != set(DEFAULT_POLICY):
        raise ValueError("Invalid policy settings.")
    if (
        isinstance(values["minimum_percent"], bool)
        or not 0 <= float(values["minimum_percent"]) <= 100
    ):
        raise ValueError("Minimum attendance must be between 0 and 100.")
    if (
        isinstance(values["editing_days"], bool)
        or not isinstance(values["editing_days"], int)
        or not 0 <= values["editing_days"] <= 365
    ):
        raise ValueError("Editing window must be 0 to 365 days.")
    if not isinstance(values["late_counts_present"], bool):
        raise ValueError("Choose whether late counts as present.")  # noqa: TRY004 - form validation contract
    return values


def save_policy(user, values):
    authorize(user)
    values = validate_policy(values)
    with db.connection() as connection:
        cur = connection.cursor()
        cur.execute(
            "MERGE INTO attendance_settings s USING(SELECT 'ATTENDANCE_POLICY' setting_key FROM dual) x ON(s.setting_key=x.setting_key) WHEN MATCHED THEN UPDATE SET value_json=:value,updated_by=:actor,updated_at=CURRENT_TIMESTAMP WHEN NOT MATCHED THEN INSERT(setting_key,value_json,updated_by) VALUES('ATTENDANCE_POLICY',:value,:actor)",
            {"value": json.dumps(values), "actor": user["user_id"]},
        )
        db.audit_event(cur, user, "ATTENDANCE_POLICY_SAVED", "ATTENDANCE_POLICY")
