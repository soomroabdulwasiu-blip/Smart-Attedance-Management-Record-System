"""Show the real Windows admin hardware page using a guarded disposable schema."""

import os
import re
import time
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QScrollArea

from amrs import db, devices, gui, secure_store
from amrs.cameras import CameraConfig


def main():
    runtime = os.getenv("AMRS_DB_USERNAME", "")
    owner = os.getenv("AMRS_DB_SCHEMA", "")
    if (
        not re.fullmatch(r"AMRST_R_[A-F0-9]{10}", runtime)
        or owner != "AMRST_M_" + runtime[8:]
    ):
        raise RuntimeError("Disposable native test accounts required.")
    root = Path(__file__).resolve().parents[1]
    vault_patch = patch.object(
        devices,
        "SecretStore",
        lambda: secure_store.SecretStore(
            "camera", root / "artifacts" / "desktop-vault"
        ),
    )
    vault_patch.start()
    admin = dict(
        db.one(
            "SELECT u.user_id,u.full_name,u.email FROM users u JOIN roles r ON r.role_id=u.role_id WHERE r.role_name='ADMIN' FETCH FIRST 1 ROWS ONLY"
        ),
        role="ADMIN",
    )
    config = CameraConfig(
        "desktop-smoke-camera",
        "SIMULATED — Windows desktop verification",
        "mock",
        "mock://desktop",
    )
    devices.save_device(admin, config)
    app = QApplication([])
    app.setStyleSheet(gui.STYLE)
    login = gui.Login()
    window = gui.MainWindow(admin, login)
    window.setWindowTitle("AMRS — DEVELOPMENT VERIFICATION / SIMULATED")
    window.resize(1366, 768)
    window.show()
    window.navigate_to("Hardware & cameras")
    panel = window.hardware_panel
    started = time.monotonic()
    stage = {"connected": False, "screenshot": False}
    result = {"success": False}

    def tick():
        if not stage["connected"] and panel.rows:
            index = next(
                (
                    i
                    for i, row in enumerate(panel.rows)
                    if row["device_id"] == config.device_id
                ),
                None,
            )
            if index is not None:
                panel.table.selectRow(index)
                panel.connect_device()
                stage["connected"] = True
        if (
            panel.capture
            and panel.capture.latest is not None
            and not stage["screenshot"]
        ):
            panel.render_preview()
            page = window.tabs.currentWidget()
            if isinstance(page, QScrollArea):
                page.ensureWidgetVisible(panel.preview)
            window.grab().save(str(root / "artifacts" / "desktop-hardware.png"))
            stage["screenshot"] = True
            panel.disconnect_device()
        if (
            stage["screenshot"]
            and not (panel.capture and panel.capture.isRunning())
            and not panel.tasks
        ):
            window.close()
            if not window.isVisible():
                login.close()
                result["success"] = True
                timer.stop()
                app.quit()
        if time.monotonic() - started > 30:
            panel.disconnect_device()
            window.close()
            if not (panel.capture and panel.capture.isRunning()):
                timer.stop()
                app.exit(1)

    timer = QTimer()
    timer.setInterval(100)
    timer.timeout.connect(tick)
    timer.start()
    code = app.exec()
    devices.remove_device(admin, config.device_id)
    print(
        "Windows desktop and simulated live preview: "
        + ("passed" if result["success"] else "failed")
    )
    return 0 if code == 0 and result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
