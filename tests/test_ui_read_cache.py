"""Background refresh renders without a second foreground database query."""

import contextlib
import time

from PySide6.QtCore import QEventLoop, QThreadPool, QTimer
from PySide6.QtWidgets import QApplication, QMainWindow

from amrs import db, gui, ui_reads


def test_refresh_snapshot_keeps_ui_responsive_and_avoids_second_query(monkeypatch):
    assert QThreadPool.globalInstance().waitForDone(10000)
    QApplication.processEvents()
    calls = []
    events = []

    class Cursor:
        description = (("STUDENT_ID",),)

        def execute(self, *args):
            calls.append(True)
            time.sleep(0.2)

        def __iter__(self):
            return iter([("synthetic",)])

    @contextlib.contextmanager
    def connection():
        class Connection:
            def cursor(self):
                return Cursor()

        yield Connection()

    monkeypatch.setattr(db, "connection", connection)
    monkeypatch.setattr(gui, "error", lambda p, e: events.append("error"))

    class Window(QMainWindow):
        submit_action = gui.MainWindow.submit_action

        def __init__(self):
            super().__init__()
            self._async_mode = True
            self._action_tasks = set()
            self.user = {"role": "ADMIN", "user_id": "test"}

    window = Window()

    def render(w):
        w.result = db.students()
        events.append("render")

    wrapped = ui_reads.background_read(render, "refresh_students")
    started = time.monotonic()
    wrapped(window)
    assert time.monotonic() - started < 0.1
    QTimer.singleShot(30, lambda: events.append("heartbeat"))
    loop = QEventLoop()
    QTimer.singleShot(700, loop.quit)
    loop.exec()
    assert (
        events == ["heartbeat", "render"]
        and len(calls) == 1
        and window.result == [{"student_id": "synthetic"}]
    )
    window.close()
