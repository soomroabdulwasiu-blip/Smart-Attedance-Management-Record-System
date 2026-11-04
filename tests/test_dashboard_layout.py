"""Every role page remains usable at all supported desktop window sizes."""

import pytest
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication

from amrs import academic, db, devices, gui


@pytest.mark.parametrize("role", ["ADMIN", "TEACHER", "STUDENT"])
@pytest.mark.parametrize("size", [(950, 650), (1280, 720), (1366, 768), (1920, 1080)])
def test_all_dashboard_pages_fit(role, size, monkeypatch):
    errors = []
    monkeypatch.setattr(gui, "error", lambda p, e: errors.append(str(e)))
    for name in (
        "students",
        "teachers",
        "courses",
        "departments",
        "attendance",
        "student_summary",
        "pending_resets",
        "pending_teacher_signups",
        "correction_requests",
        "audit_records",
    ):
        monkeypatch.setattr(db, name, lambda *args, **kwargs: [])
    monkeypatch.setattr(db, "one", lambda *args, **kwargs: {"n": 0})
    monkeypatch.setattr(
        db, "_attendance_policy", lambda *args: dict(academic.DEFAULT_POLICY)
    )
    monkeypatch.setattr(
        db,
        "teacher_dashboard_stats",
        lambda *args: {"course_count": 0, "student_count": 0, "record_count": 0},
    )
    monkeypatch.setattr(db, "session_is_active", lambda *args: True)
    monkeypatch.setattr(db, "student_profile", lambda *args: {})
    monkeypatch.setattr(devices, "list_devices", lambda *args: [])
    monkeypatch.setattr(academic, "classes", lambda *args: [])
    monkeypatch.setattr(
        academic, "get_policy", lambda *args: dict(academic.DEFAULT_POLICY)
    )
    app = QApplication.instance()
    app.setStyleSheet(gui.STYLE)
    login = gui.Login()
    window = gui.MainWindow(
        {
            "role": role,
            "user_id": "test-principal",
            "full_name": "Layout verification",
            "email": "layout@example.test",
        },
        login,
    )
    window.resize(*size)
    window.show()
    app.processEvents()
    for i in range(window.tabs.count()):
        window.select_tab(i)
        app.processEvents()
        assert window.tabs.widget(i).horizontalScrollBar().maximum() == 0, (
            role,
            window.page_titles[i],
            size,
        )
    assert not errors
    assert QThreadPool.globalInstance().waitForDone(5000)
    app.processEvents()
    window.close()
    login.close()
