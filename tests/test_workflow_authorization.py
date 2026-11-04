"""Authorization, duplicate protection and audit transaction regressions.

Oracle cases run only in the native harness's disposable runtime/owner pair.
No production configuration or biometric fixtures are used.
"""

import contextlib
import json
import os
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

import oracledb
import pytest

from amrs import db

TEACHER = {"role": "TEACHER", "user_id": "T"}


def no_query(*args, **kwargs):
    raise AssertionError("Unauthorized input reached a database query")


@pytest.mark.parametrize("role", ["", "GUEST", "admin", None])
def test_invalid_login_role_never_queries_database(monkeypatch, role):
    monkeypatch.setattr(db, "one", no_query)
    with pytest.raises(ValueError, match="role"):
        db.login(role, "person@example.test", "not-a-real-password")


@pytest.mark.parametrize("principal", [{"role": "GUEST", "user_id": "X"}, {}, None])
def test_invalid_principal_cannot_read_attendance(monkeypatch, principal):
    monkeypatch.setattr(db, "rows", no_query)
    with pytest.raises(ValueError):
        db.attendance(principal)


def test_unknown_role_cannot_fall_through_to_all_courses(monkeypatch):
    monkeypatch.setattr(db, "rows", no_query)
    with pytest.raises(ValueError):
        db.courses({"role": "GUEST", "user_id": "X"})


@pytest.mark.parametrize("score", [None, 0.1, float("nan"), float("inf"), 1.01, True])
def test_unreliable_face_score_is_rejected_before_database_access(score):
    with pytest.raises(ValueError, match="confidence"):
        db._mark(None, TEACHER, "C", "S", date.today(), "PRESENT", "FACE", score)


def test_unknown_method_and_automated_absence_are_rejected():
    with pytest.raises(ValueError):
        db._mark(None, TEACHER, "C", "S", date.today(), "PRESENT", "IMPORT", None)
    with pytest.raises(ValueError, match="absence"):
        db._mark(None, TEACHER, "C", "S", date.today(), "ABSENT", "QR", None)


def test_non_face_method_cannot_supply_a_biometric_score():
    with pytest.raises(ValueError, match="only valid"):
        db._mark(None, TEACHER, "C", "S", date.today(), "PRESENT", "QR", 0.9)


def test_cross_student_and_teacher_dashboard_reads_are_rejected(monkeypatch):
    monkeypatch.setattr(db, "one", no_query)
    monkeypatch.setattr(db, "rows", no_query)
    with pytest.raises(ValueError, match="own"):
        db.student_summary("OTHER", {"role": "STUDENT", "user_id": "S"})
    with pytest.raises(ValueError, match="own"):
        db.teacher_dashboard_stats("OTHER", TEACHER)


def test_unassigned_teacher_report_is_rejected_before_loading_data(monkeypatch):
    monkeypatch.setattr(db, "one", lambda *args: None)
    monkeypatch.setattr(db, "rows", no_query)
    with pytest.raises(ValueError, match="not assigned"):
        db.course_summary(TEACHER, "C")


def test_student_cannot_access_audit_records(monkeypatch):
    monkeypatch.setattr(db, "rows", no_query)
    with pytest.raises(ValueError):
        db.audit_records({"role": "STUDENT", "user_id": "S"})


def test_password_change_checks_authenticated_account_identity(monkeypatch):
    monkeypatch.setattr(db, "login", lambda *args: {"user_id": "OTHER"})
    monkeypatch.setattr(db, "hash_password", no_query)
    with pytest.raises(ValueError, match="identity"):
        db.change_password(dict(TEACHER, email="teacher@example.test"), "old", "new")


def test_audit_failure_rolls_back_attendance_wrapper(monkeypatch):
    outcomes = []

    @contextlib.contextmanager
    def transaction():
        class Connection:
            def cursor(self):
                return object()

        try:
            yield Connection()
        except Exception:
            outcomes.append("rollback")
            raise
        else:
            outcomes.append("commit")

    monkeypatch.setattr(db, "connection", transaction)
    monkeypatch.setattr(db, "_mark", lambda *args: True)

    def unavailable_audit(*args):
        raise RuntimeError("Audit write failed")

    monkeypatch.setattr(db, "audit_event", unavailable_audit)
    with pytest.raises(RuntimeError):
        db.mark_attendance(TEACHER, "C", "S", date.today())
    assert outcomes == ["rollback"]


def test_duplicate_checkin_does_not_add_another_audit_event(monkeypatch):
    @contextlib.contextmanager
    def transaction():
        class Connection:
            def cursor(self):
                return object()

        yield Connection()

    monkeypatch.setattr(db, "connection", transaction)
    monkeypatch.setattr(db, "_mark", lambda *args: False)
    monkeypatch.setattr(db, "audit_event", no_query)
    assert db.mark_attendance(TEACHER, "C", "S", date.today(), method="QR") is False


def test_read_snapshot_prevents_foreground_io_and_returns_independent_rows(monkeypatch):
    calls = []

    class Cursor:
        description = (("COUNT",),)

        def execute(self, sql, params):
            calls.append((sql, params))

        def __iter__(self):
            return iter([(5,)])

    @contextlib.contextmanager
    def transaction():
        class Connection:
            def cursor(self):
                return Cursor()

        yield Connection()

    monkeypatch.setattr(db, "connection", transaction)
    with db.capture_reads() as snapshot:
        assert db.rows("SELECT :id count FROM dual", {"id": "S"}) == [{"count": 5}]
    with db.use_reads(snapshot):
        result = db.rows("SELECT   :id count FROM dual", {"id": "S"})
        result[0]["count"] = 999
        assert db.rows("SELECT :id count FROM dual", {"id": "S"}) == [{"count": 5}]
        with pytest.raises(db.ReadSnapshotMiss):
            db.rows("SELECT :id count FROM dual", {"id": "OTHER"})
    assert len(calls) == 1
    with db.use_reads(snapshot), ThreadPoolExecutor(max_workers=1) as executor:
        assert executor.submit(db.rows, "SELECT 1 count FROM dual").result() == [
            {"count": 5}
        ]
    assert len(calls) == 2  # A different thread never inherits the GUI snapshot.


@pytest.mark.parametrize(
    "policy",
    [
        {"editing_days": -1},
        {"late_counts_present": "yes"},
        {"minimum_percent": 101},
        [],
    ],
)
def test_corrupt_policy_is_not_silently_applied(monkeypatch, policy):
    monkeypatch.setattr(db, "one", lambda *args: {"value_json": json.dumps(policy)})
    with pytest.raises(ValueError, match="administrator review"):
        db._attendance_policy()


def test_date_filters_reject_reversed_dates_before_query(monkeypatch):
    monkeypatch.setattr(db, "rows", no_query)
    with pytest.raises(ValueError, match="Start date"):
        db.attendance(
            TEACHER, start_date=date.today(), end_date=date.today() - timedelta(days=1)
        )


def test_expired_correction_window_is_enforced():
    with pytest.raises(ValueError, match="window has closed"):
        db._check_edit_window(datetime.now() - timedelta(days=4), {"editing_days": 3})
    db._check_edit_window(date.today(), {"editing_days": 0})


def test_historical_manual_guard_allows_initial_rows_but_protects_existing(monkeypatch):
    monkeypatch.setattr(db, "_attendance_policy", lambda *args: {"editing_days": 3})

    class Cursor:
        def execute(self, *args):
            pass

        def __iter__(self):
            return iter([("EXISTING",)])

    day = date.today() - timedelta(days=4)
    db._guard_manual_edits(Cursor(), "C", day, ["NEW"])
    with pytest.raises(ValueError, match="window has closed"):
        db._guard_manual_edits(Cursor(), "C", day, ["EXISTING"])


def disposable_oracle_enabled():
    owner = os.getenv("AMRS_DB_SCHEMA", "")
    runtime = os.getenv("AMRS_DB_USERNAME", "")
    return (
        os.getenv("AMRS_TEST_ORACLE") == "1"
        and bool(re.fullmatch(r"AMRST_M_[A-F0-9]{10}", owner))
        and runtime == owner.replace("AMRST_M_", "AMRST_R_", 1)
    )


native = pytest.mark.skipif(
    not disposable_oracle_enabled(),
    reason="Requires guarded disposable native Oracle schemas",
)


@pytest.fixture
def oracle_workflow():
    assert disposable_oracle_enabled(), "Refusing a non-disposable Oracle target"
    tag = uuid.uuid4().hex[:12].upper()
    dept = db.departments()[0]["dept_id"]
    db.signup_teacher(
        "Authorization fixture",
        "t" + tag.lower() + "@example.test",
        "Test-password-123",
        "Testing",
    )
    teacher = db.login(
        "TEACHER", "t" + tag.lower() + "@example.test", "Test-password-123"
    )
    db.signup_student(
        "Authorization fixture",
        "s" + tag.lower() + "@example.test",
        "Test-password-123",
        "R" + tag,
        dept,
        1,
        2026,
    )
    student = db.login("STUDENT", "R" + tag, "Test-password-123")
    db.add_course("C" + tag, "Authorization fixture", 3, dept, teacher["user_id"], 1)
    course = db.course_for_code("C" + tag)["course_id"]
    db.enroll_student(course, student["user_id"])
    admin = db.one(
        "SELECT u.user_id FROM users u JOIN roles r ON r.role_id=u.role_id WHERE r.role_name='ADMIN' AND u.is_active=1 FETCH FIRST 1 ROW ONLY"
    )
    admin["role"] = "ADMIN"
    try:
        yield teacher, student, course, admin
    finally:
        db.delete_student_permanently(student["user_id"])
        db.delete_teacher_permanently(teacher["user_id"])


@native
def test_oracle_automated_checkin_preserves_manual_result_and_method(oracle_workflow):
    teacher, student, course, _ = oracle_workflow
    sid = student["user_id"]
    db.mark_attendance(teacher, course, sid, date.today(), "PRESENT", "MANUAL")
    assert (
        db.mark_attendance(teacher, course, sid, date.today(), "PRESENT", "FACE", 0.9)
        is False
    )
    assert (
        db.mark_attendance(teacher, course, sid, date.today(), "PRESENT", "QR") is False
    )
    record = db.attendance(student, course)[0]
    assert (record["status"], record["check_in_method"]) == ("PRESENT", "MANUAL")
    db.correct_attendance(
        teacher, record["attendance_id"], "ABSENT", "Reviewed by assigned teacher"
    )
    with pytest.raises(ValueError, match="review it manually"):
        db.mark_attendance(teacher, course, sid, date.today(), "PRESENT", "FACE", 0.9)
    assert db.attendance(student, course)[0]["status"] == "ABSENT"


@native
def test_oracle_policy_changes_percentage_and_date_scoped_reports(oracle_workflow):
    teacher, student, course, admin = oracle_workflow
    for offset, status in [(2, "PRESENT"), (1, "LATE"), (0, "ABSENT")]:
        db.mark_attendance(
            teacher,
            course,
            student["user_id"],
            date.today() - timedelta(days=offset),
            status,
        )
    original = db.one(
        "SELECT value_json FROM attendance_settings WHERE setting_key='ATTENDANCE_POLICY'"
    )
    try:
        with db.connection() as connection:
            connection.cursor().execute(
                """MERGE INTO attendance_settings s USING (SELECT 'ATTENDANCE_POLICY' setting_key FROM dual) x
                ON (s.setting_key=x.setting_key) WHEN MATCHED THEN UPDATE SET s.value_json=:value,s.updated_by=:actor
                WHEN NOT MATCHED THEN INSERT(setting_key,value_json,updated_by) VALUES(x.setting_key,:value,:actor)""",
                {
                    "value": json.dumps(
                        {
                            "minimum_percent": 75,
                            "editing_days": 3,
                            "late_counts_present": False,
                        }
                    ),
                    "actor": admin["user_id"],
                },
            )
        result = db.course_summary(teacher, course)[0]
        assert result["attendance_pct"] == pytest.approx(33.33)
        assert result["meets_minimum"] is False
        assert db.student_summary(student["user_id"], student)[0][
            "attendance_pct"
        ] == pytest.approx(33.33)
        scoped = db.course_summary(
            teacher,
            course,
            date.today() - timedelta(days=2),
            date.today() - timedelta(days=1),
        )[0]
        assert scoped["total_sessions"] == 2 and scoped["attendance_pct"] == 50
        assert (
            len(
                db.attendance(
                    student, course, date.today() - timedelta(days=1), date.today()
                )
            )
            == 2
        )
    finally:
        with db.connection() as connection:
            if original:
                connection.cursor().execute(
                    "UPDATE attendance_settings SET value_json=:value WHERE setting_key='ATTENDANCE_POLICY'",
                    {"value": original["value_json"]},
                )
            else:
                connection.cursor().execute(
                    "DELETE FROM attendance_settings WHERE setting_key='ATTENDANCE_POLICY'"
                )


@native
def test_oracle_audit_is_transactional_and_runtime_cannot_rewrite_it(oracle_workflow):
    teacher, student, course, admin = oracle_workflow
    db.mark_attendance(teacher, course, student["user_id"], date.today(), "ABSENT")
    record = db.attendance(student, course)[0]
    db.request_attendance_correction(
        student, record["attendance_id"], "PRESENT", "Fixture correction"
    )
    request = db.correction_requests(teacher)[0]
    db.resolve_attendance_request(teacher, request["request_id"], True)
    events = db.audit_records(admin, 1000)
    assert any(
        e["action"] == "ATTENDANCE_REQUEST_APPROVED"
        and e["entity_id"] == str(record["attendance_id"])
        for e in events
    )
    for sql in (
        "DELETE FROM app_audit WHERE 1=0",
        "UPDATE app_audit SET detail='changed' WHERE 1=0",
    ):
        with (
            pytest.raises(oracledb.DatabaseError) as error,
            db.connection() as connection,
        ):
            connection.cursor().execute(sql)
        # Oracle 26ai reports missing object grants as ORA-41900; older releases
        # use ORA-01031. Both must deny the operation, not silently succeed.
        assert error.value.args[0].code in (1031,41900)


@native
def test_oracle_expired_and_unauthorized_corrections_preserve_records(oracle_workflow):
    teacher, student, course, _ = oracle_workflow
    old = date.today() - timedelta(days=4)
    db.mark_attendance(teacher, course, student["user_id"], old, "PRESENT")
    record = db.attendance(student, course)[0]
    with pytest.raises(ValueError, match="window has closed"):
        db.correct_attendance(teacher, record["attendance_id"], "ABSENT", "Too old")
    with pytest.raises(ValueError, match="window has closed"):
        db.mark_attendance(teacher, course, student["user_id"], old, "ABSENT")
    with pytest.raises(ValueError, match="window has closed"):
        db.mark_bulk(teacher, course, old, [(student["user_id"], "ABSENT")])
    db.mark_attendance(
        teacher, course, student["user_id"], old - timedelta(days=1), "PRESENT"
    )
    with pytest.raises(ValueError):
        db.mark_attendance(
            {"role": "TEACHER", "user_id": str(uuid.uuid4())},
            course,
            student["user_id"],
            date.today(),
        )
    assert all(row["status"] == "PRESENT" for row in db.attendance(student, course))
