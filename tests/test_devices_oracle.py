"""Native Oracle device, class and consent workflows using disposable fixtures."""

import hashlib
import os
import time
import uuid
from datetime import UTC, date, datetime

import cv2
import numpy as np
import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from amrs import (
    academic,
    db,
    devices,
    face,
    gui,
    presentation_data,
    privacy,
    secure_store,
)
from amrs.cameras import CameraConfig

pytestmark = pytest.mark.skipif(
    os.getenv("AMRS_TEST_ORACLE") != "1",
    reason="Requires disposable native Oracle schemas",
)


@pytest.fixture
def setup(monkeypatch, tmp_path):
    admin = dict(
        db.one(
            "SELECT u.user_id FROM users u JOIN roles r ON r.role_id=u.role_id WHERE r.role_name='ADMIN' FETCH FIRST 1 ROWS ONLY"
        ),
        role="ADMIN",
    )
    monkeypatch.setattr(
        devices,
        "SecretStore",
        lambda: secure_store.SecretStore("camera", tmp_path / "vault"),
    )
    monkeypatch.setattr(face, "FACE_DIR", tmp_path / "faces")
    monkeypatch.setattr(face, "LEGACY_FACE_DIR", tmp_path / "legacy")
    tag = uuid.uuid4().hex[:10].upper()
    dept = db.departments()[0]["dept_id"]
    pw = "Integration-password-123"
    db.signup_teacher(
        "Device test teacher",
        "td" + tag.lower() + "@example.test",
        pw,
        "Test department",
        actor=admin,
    )
    teacher = db.login("TEACHER", "td" + tag.lower() + "@example.test", pw)
    db.signup_student(
        "Device test student",
        "sd" + tag.lower() + "@example.test",
        pw,
        "D" + tag,
        dept,
        1,
        2026,
    )
    student = db.login("STUDENT", "D" + tag, pw)
    db.add_course(
        "D" + tag, "Device fixture course", 3, dept, teacher["user_id"], 1, actor=admin
    )
    course = next(
        r["course_id"] for r in db.courses(teacher) if r["course_code"] == "D" + tag
    )
    db.enroll_student(course, student["user_id"], actor=admin)
    created_devices = []
    created_classes = []
    yield (
        admin,
        teacher,
        student,
        course,
        dept,
        created_devices,
        created_classes,
        tmp_path,
    )
    for device_id in created_devices:
        if any(r["device_id"] == device_id for r in devices.list_devices(admin)):
            devices.remove_device(admin, device_id)
    for class_id in created_classes:
        if any(r["class_id"] == class_id for r in academic.classes(admin)):
            academic.delete_class(admin, class_id)
    db.delete_course_permanently(course, actor=admin)
    db.delete_student_permanently(student["user_id"], actor=admin)
    db.delete_teacher_permanently(teacher["user_id"], actor=admin)


def test_device_save_encrypted_credentials_selection_disable_remove_and_scope(setup):
    admin, teacher, student, _course, _dept, ids, _, _tmp = setup
    first = CameraConfig(
        str(uuid.uuid4()), "SIMULATED integration camera", "mock", "mock://native"
    )
    second = CameraConfig(
        str(uuid.uuid4()), "SIMULATED second camera", "mock", "mock://second"
    )
    for config in (first, second):
        devices.save_device(admin, config)
        ids.append(config.device_id)
    credential = {
        "username": "synthetic-camera-user",
        "password": "Synthetic-camera-secret-123",
        "mode": "digest",
    }
    devices.save_device(admin, first, credentials=credential)
    row = next(
        r for r in devices.list_devices(admin) if r["device_id"] == first.device_id
    )
    assert (
        "password" not in row["config_json"]
        and credential["password"] not in row["config_json"]
    )
    vault = devices.SecretStore()
    assert vault.get(first.device_id) == credential
    assert credential["password"].encode() not in vault.path.read_bytes()
    devices.select_active(admin, first.device_id)
    devices.select_active(admin, second.device_id)
    assert sum(r["is_active_source"] for r in devices.list_devices(admin)) == 1
    assert devices.active_device(teacher)["device_id"] == second.device_id
    devices.save_device(admin, second, enabled=False)
    assert devices.active_device(teacher) is None
    with pytest.raises(ValueError):
        devices.select_active(admin, second.device_id)
    with pytest.raises(ValueError):
        devices.list_devices(student)
    with pytest.raises(ValueError):
        devices.save_device(teacher, first)
    adapter = devices.adapter_for(teacher, first.device_id)
    assert adapter.connect()
    assert adapter.read_frame()[0]
    adapter.release()
    devices.record_status(
        admin, first.device_id, "ERROR", "password must never be persisted here"
    )
    row = next(
        r for r in devices.list_devices(admin) if r["device_id"] == first.device_id
    )
    assert row["status"] == "ERROR" and "password" not in row["last_error"]
    devices.remove_device(admin, first.device_id)
    assert vault.get(first.device_id) is None
    assert any(r["action"] == "DEVICE_REMOVED" for r in db.audit_records(admin))


def test_classes_scope_assignment_mismatch_and_delete_preserve_attendance(setup):
    admin, teacher, student, course, dept, _, ids, _tmp = setup
    cid = academic.save_class(
        admin, "Synthetic class", dept, 1, uuid.uuid4().hex[:8], 2026
    )
    ids.append(cid)
    academic.assign_course(admin, cid, course)
    assert any(r["class_id"] == cid for r in academic.classes(teacher))
    assert any(r["class_id"] == cid for r in academic.classes(student))
    wrong = academic.save_class(
        admin, "Other semester", dept, 2, uuid.uuid4().hex[:8], 2026
    )
    ids.append(wrong)
    with pytest.raises(ValueError):
        academic.assign_course(admin, wrong, course)
    with pytest.raises(ValueError):
        academic.save_class(teacher, "Forbidden", dept, 1, "A", 2026)
    db.mark_attendance(teacher, course, student["user_id"], date.today(), "PRESENT")
    academic.delete_class(admin, cid)
    assert len(db.attendance(student, course)) == 1 and any(
        r["course_id"] == course for r in db.courses(student)
    )


def test_consent_encrypted_template_and_revocation(setup, monkeypatch):
    admin, _teacher, student, course, _dept, _, _, _tmp = setup
    sid = student["user_id"]
    engine = face.FaceEngine.__new__(face.FaceEngine)
    monkeypatch.setattr(engine, "detect", lambda image: [np.zeros(15, dtype="float32")])
    monkeypatch.setattr(engine, "encode", lambda *args: np.ones(128, dtype="float32"))
    ok, image = cv2.imencode(".png", np.zeros((64, 64, 3), dtype="uint8"))
    assert ok
    with pytest.raises(ValueError, match="consent"):
        engine.save_reference_bytes(sid, image.tobytes())
    privacy.record_consent(admin, sid, True)
    engine.save_reference_bytes(sid, image.tobytes())
    target = face.FACE_DIR / (sid + ".template")
    assert target.is_file() and not (face.FACE_DIR / (sid + ".image")).exists()
    assert sid.encode() not in target.read_bytes()
    refs, skipped = engine.load_references(db.course_students(course))
    assert len(refs) == 1 and not skipped
    privacy.revoke(admin, sid)
    assert not target.exists() and not privacy.has_consent(sid)
    assert not db.one(
        "SELECT face_enrolled FROM students WHERE student_id=:id", {"id": sid}
    )["face_enrolled"]


def test_real_initial_read_snapshot_and_all_role_pages_at_supported_sizes(
    setup, monkeypatch
):
    admin, teacher, student, *_ = setup
    errors = []
    monkeypatch.setattr(
        gui,
        "error",
        lambda parent, exc: errors.append(type(exc).__name__ + ": " + str(exc)),
    )
    app = QApplication.instance()
    app.setStyleSheet(gui.STYLE)
    for principal in (admin, teacher, student):
        principal = dict(principal)
        if "full_name" not in principal:
            principal.update(
                db.one(
                    "SELECT full_name,email FROM users WHERE user_id=:id",
                    {"id": principal["user_id"]},
                )
            )
        principal["_initial_reads"] = presentation_data.prefetch(principal)
        login = gui.Login()
        window = gui.MainWindow(principal, login)
        window.show()
        for width, height in ((950, 650), (1280, 720), (1366, 768), (1920, 1080)):
            window.resize(width, height)
            app.processEvents()
            for i in range(window.tabs.count()):
                window.select_tab(i)
                app.processEvents()
                assert window.tabs.widget(i).horizontalScrollBar().maximum() == 0, (
                    principal["role"],
                    window.page_titles[i],
                    width,
                )
        window.close()
        deadline = time.monotonic() + 10
        while window.isVisible() and time.monotonic() < deadline:
            app.processEvents()
            QTest.qWait(10)
        assert not window.isVisible()
        login.close()
    assert not errors, errors


def test_native_purge_is_backup_bound_and_preserves_active_attendance(setup):
    from amrs import maintenance

    admin, teacher, student, course, dept, _, _, tmp = setup
    db.mark_attendance(teacher, course, student["user_id"], date.today(), "PRESENT")
    sid = db.add_student(
        "Synthetic inactive cleanup",
        uuid.uuid4().hex[:16],
        "",
        "",
        dept,
        1,
        2026,
        actor=admin,
    )
    with db.connection() as connection:
        connection.cursor().execute(
            "UPDATE students SET is_active=0 WHERE student_id=:id", {"id": sid}
        )
    plan = maintenance.purge_inactive_records()
    assert db.one("SELECT student_id FROM students WHERE student_id=:id", {"id": sid})
    with pytest.raises(ValueError):
        maintenance.purge_inactive_records(confirm=True, approval={}, user=admin)
    approval = {
        "plan_sha256": maintenance.digest(plan),
        "approved": True,
        "restore_verified": True,
        "approved_by": "Synthetic fixture only",
        "approved_at": datetime.now(UTC).isoformat(),
    }
    for key in ("backup", "restore_report"):
        file = tmp / (key + ".fixture")
        file.write_bytes(b"Not a production backup; synthetic binding test")
        approval[key + "_file"] = str(file.resolve())
        approval[key + "_sha256"] = hashlib.sha256(file.read_bytes()).hexdigest()
    result = maintenance.purge_inactive_records(
        confirm=True, approval=approval, user=admin
    )
    assert result["executed"] and not db.one(
        "SELECT student_id FROM students WHERE student_id=:id", {"id": sid}
    )
    assert len(db.attendance(student, course)) == 1


def test_simulated_camera_multi_face_pipeline_persists_each_student_once(
    setup, monkeypatch
):
    admin, teacher, student, course, dept, ids, _, _tmp = setup
    tag = uuid.uuid4().hex[:12]
    password = "Synthetic-password-123"
    db.signup_student(
        "Second synthetic participant",
        tag + "@example.test",
        password,
        "S" + tag.upper(),
        dept,
        1,
        2026,
    )
    second = db.login("STUDENT", tag + "@example.test", password)
    db.enroll_student(course, second["user_id"], actor=admin)
    for item in (student, second):
        privacy.record_consent(admin, item["user_id"], True)
        db.set_face_enrolled(item["user_id"])
    participants = [student["user_id"], second["user_id"]]
    vectors = np.eye(3, 128, dtype="float32")

    class Engine:
        def load_references(self, rows):
            return [
                (row, vectors[participants.index(row["student_id"])]) for row in rows
            ], []

        def detect(self, frame):
            return [
                np.array([20, 20, 40, 50]),
                np.array([120, 20, 40, 50]),
                np.array([220, 20, 40, 50]),
            ]

        def encode(self, frame, box):
            return vectors[int((box[0] - 20) / 100)]

    monkeypatch.setattr(face, "FaceEngine", Engine)
    config = CameraConfig(
        str(uuid.uuid4()),
        "SIMULATED multi-face Oracle fixture",
        "mock",
        "mock://oracle",
        simulation_profile="interruption",
    )
    devices.save_device(admin, config)
    ids.append(config.device_id)
    events = []
    frames = []
    worker = face.CameraWorker(
        teacher, course, date.today(), "device:" + config.device_id, mirror=True
    )
    worker.attendance_saved.connect(lambda *args: events.append(args))
    worker.frame_ready.connect(frames.append)
    try:
        worker.start()
        deadline = time.monotonic() + 4
        while len(events) < 2 and time.monotonic() < deadline:
            QApplication.processEvents()
            QTest.qWait(10)
        assert worker.stop()
        QApplication.processEvents()
        rows = db.attendance(teacher, course)
        assert (
            len(rows) == 2
            and {row["student_id"] for row in rows} == set(participants)
            and all(row["check_in_method"] == "FACE" for row in rows)
        )
        assert len(events) == 2
        assert any(
            np.any(np.all(frame == [0, 200, 0], axis=2))
            and np.any(np.all(frame == [0, 0, 255], axis=2))
            for frame in frames
        )
    finally:
        assert worker.stop()
        db.delete_student_permanently(second["user_id"], actor=admin)
