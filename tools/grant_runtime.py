"""Grant a separate runtime account DML access to an AMRS owner's objects."""

import re

TABLES = (
    "ROLES",
    "DEPARTMENTS",
    "USERS",
    "STUDENTS",
    "STUDENT_LOGINS",
    "COURSES",
    "COURSE_ENROLLMENTS",
    "ATTENDANCE",
    "CHECKIN_SESSIONS",
    "PASSWORD_RESET_REQUESTS",
    "TEACHER_SIGNUP_REQUESTS",
    "ATTENDANCE_CORRECTION_REQUESTS",
    "EMAIL_PASSWORD_RESETS",
    "CAMERA_DEVICES",
    "BIOMETRIC_CONSENTS",
    "ATTENDANCE_SETTINGS",
    "ACADEMIC_CLASSES",
)


def grant_runtime(connection, username):
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,29}", username):
        raise ValueError("Use a simple uppercase Oracle runtime account name.")
    cur = connection.cursor()
    cur.execute("SELECT sys_context('USERENV','CURRENT_SCHEMA') FROM dual")
    owner = cur.fetchone()[0]
    if owner == username:
        raise ValueError("Runtime user must differ from schema/migration owner.")
    for table in TABLES:
        privileges = (
            "SELECT"
            if table in ("ROLES", "DEPARTMENTS")
            else "SELECT, INSERT, UPDATE, DELETE"
        )
        cur.execute(f"GRANT {privileges} ON {table} TO {username}")
    for obj in ("VW_ATTENDANCE_SUMMARY", "SCHEMA_MIGRATIONS"):
        cur.execute(f"GRANT SELECT ON {obj} TO {username}")
    cur.execute(f"GRANT SELECT, INSERT ON app_audit TO {username}")
