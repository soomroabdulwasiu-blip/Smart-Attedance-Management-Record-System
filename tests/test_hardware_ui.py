"""Real hardware widgets with deterministic camera/repository substitutes.

These exercise Qt workers and form actions without Oracle production records,
real credentials, network endpoints or physical cameras.
"""

import json
import threading
import time
from dataclasses import asdict

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QScrollArea

from amrs import cameras, devices, hardware_ui, secure_store
from amrs.gui import STYLE

ADMIN = {"role": "ADMIN", "user_id": "test-admin"}


def wait_until(predicate, timeout=2500):
    deadline = time.monotonic() + timeout / 1000
    while not predicate() and time.monotonic() < deadline:
        QApplication.processEvents()
        QTest.qWait(10)
    assert predicate(), "Qt action did not complete before the test deadline."


def row_for(config, enabled=True):
    values = asdict(config)
    return {
        "device_id": config.device_id,
        "name": config.name,
        "device_type": config.device_type,
        "endpoint": config.source,
        "enabled": int(enabled),
        "is_active_source": 0,
        "config_json": json.dumps({key: values[key] for key in devices.CONFIG_FIELDS}),
        "status": "DISCONNECTED",
        "last_error": None,
        "last_connected": None,
    }


@pytest.fixture
def memory_repository(monkeypatch):
    rows = []
    statuses = []
    saves = []
    secrets = {}

    class Vault:
        def get(self, key):
            return secrets.get(key)

        def set(self, key, value):
            secrets[key] = value

    def save(user, config, enabled=True, credentials=None):
        cameras.validate_config(config)
        saves.append(config)
        current = next((i for i in rows if i["device_id"] == config.device_id), None)
        if current:
            current.update(row_for(config, enabled))
        else:
            rows.append(row_for(config, enabled))
        if credentials is not None:
            secrets[config.device_id] = credentials
        return config.device_id

    def record(user, device_id, state, error="", connected=False):
        statuses.append((device_id, state, bool(error)))
        found = next(item for item in rows if item["device_id"] == device_id)
        found["status"] = state
        found["last_error"] = "Connection failed" if error else None
        if connected:
            found["last_connected"] = "test-observation"

    def active(user, device_id):
        for item in rows:
            item["is_active_source"] = int(item["device_id"] == device_id)

    def adapter(user, device_id):
        found = next(item for item in rows if item["device_id"] == device_id)
        return cameras.create_adapter(devices.config_from_row(found))

    monkeypatch.setattr(
        devices, "list_devices", lambda user: [dict(item) for item in rows]
    )
    monkeypatch.setattr(devices, "save_device", save)
    monkeypatch.setattr(devices, "record_status", record)
    monkeypatch.setattr(devices, "select_active", active)
    monkeypatch.setattr(devices, "adapter_for", adapter)
    monkeypatch.setattr(secure_store, "SecretStore", Vault)
    return {"rows": rows, "statuses": statuses, "saves": saves, "secrets": secrets}


def test_capture_worker_connects_and_releases_without_blocking_ui():
    config = cameras.CameraConfig("mock-test", "SIMULATED test", "mock", "mock://test")
    adapter = cameras.create_adapter(config)
    thread_ids = []

    def factory():
        thread_ids.append(threading.get_ident())
        time.sleep(0.15)
        return adapter

    worker = hardware_ui.CaptureTask(factory)
    ticks = []
    timer = QTimer()
    timer.setInterval(10)
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start()
    worker.start()
    try:
        wait_until(lambda: worker.latest is not None)
        assert len(ticks) >= 5
        assert thread_ids[0] != threading.get_ident()
        assert worker.info["simulated"] is True
        assert worker.info["resolution"] == (640, 480)
    finally:
        timer.stop()
        worker.request_stop()
        assert worker.wait(1500)
    assert (
        worker.latest is None and not adapter.is_connected() and not worker.last_error
    )


def test_capture_worker_recovers_stream_interruption_with_bounded_adapter():
    config = cameras.CameraConfig(
        "mock-fault",
        "SIMULATED fault",
        "mock",
        "mock://fault",
        simulation_profile="interruption",
    )
    adapter = cameras.create_adapter(config)
    worker = hardware_ui.CaptureTask(lambda: adapter)
    messages = []
    worker.status.connect(messages.append)
    worker.start()
    try:
        wait_until(lambda: adapter._frame_index >= 6)
        wait_until(lambda: any("Reconnecting" in message for message in messages))
        assert worker.latest is not None and not worker.last_error
    finally:
        worker.request_stop()
        assert worker.wait(1500)


def test_capture_failure_retains_safe_actionable_error():
    config = cameras.CameraConfig(
        "mock-broken",
        "SIMULATED broken",
        "mock",
        "mock://broken",
        simulation_profile="connect_failure",
    )
    adapter = cameras.create_adapter(config)
    worker = hardware_ui.CaptureTask(lambda: adapter)
    worker.start()
    wait_until(lambda: worker.isFinished())
    assert "SIMULATED connection failure" in worker.last_error
    assert not adapter.is_connected()


def test_hardware_panel_simulated_discovery_preview_and_disconnect(memory_repository):
    panel = hardware_ui.HardwarePanel(ADMIN)
    try:
        wait_until(lambda: not panel.tasks)
        panel.simulate()
        wait_until(lambda: len(panel.rows) == 3 and not panel.tasks)
        assert all("SIMULATED" in panel.table.item(i, 0).text() for i in range(3))
        panel.table.selectRow(0)
        panel.connect_device()
        wait_until(
            lambda: panel.capture is not None and panel.capture.latest is not None
        )
        panel.render_preview()
        assert (
            panel.preview.image is not None and "SIMULATED" in panel.diagnostics.text()
        )
        wait_until(
            lambda: any(
                state == "CONNECTED" for _, state, _ in memory_repository["statuses"]
            )
        )
        panel.disconnect_device()
        wait_until(lambda: panel.capture.isFinished() and not panel.tasks)
        wait_until(
            lambda: any(
                state == "DISCONNECTED" for _, state, _ in memory_repository["statuses"]
            )
        )
        assert panel.preview.image is None
    finally:
        panel.shutdown()
        if panel.capture:
            assert panel.capture.wait(1500)
        wait_until(lambda: not panel.tasks)
        panel.close()


def test_hardware_panel_error_persists_as_error_not_disconnected(memory_repository):
    config = cameras.CameraConfig(
        "mock-fail",
        "Broken simulation",
        "mock",
        "mock://fail",
        simulation_profile="connect_failure",
    )
    memory_repository["rows"].append(row_for(config))
    panel = hardware_ui.HardwarePanel(ADMIN)
    try:
        wait_until(lambda: bool(panel.rows) and not panel.tasks)
        assert panel.table.item(0, 0).text().startswith("SIMULATED")
        panel.table.selectRow(0)
        panel.connect_device()
        wait_until(
            lambda: (
                any(state == "ERROR" for _, state, _ in memory_repository["statuses"])
                and not panel.tasks
            )
        )
        assert memory_repository["rows"][0]["last_error"]
        assert "SIMULATED connection failure" in panel.diagnostics.text()
        assert not any(
            state == "DISCONNECTED" for _, state, _ in memory_repository["statuses"]
        )
    finally:
        panel.shutdown()
        if panel.capture:
            assert panel.capture.wait(1500)
        wait_until(lambda: not panel.tasks)
        panel.close()


def test_switching_preview_and_active_source_requires_stop(memory_repository):
    memory_repository["rows"].extend(
        row_for(item) for item in cameras.discover_simulated_devices()[:2]
    )
    panel = hardware_ui.HardwarePanel(ADMIN)
    try:
        wait_until(lambda: len(panel.rows) == 2 and not panel.tasks)
        panel.table.selectRow(0)
        panel.connect_device()
        wait_until(
            lambda: panel.capture is not None and panel.capture.latest is not None
        )
        first = panel.capture
        panel.table.selectRow(1)
        panel.connect_device()
        assert panel.capture is first and "Disconnect" in panel.notice.text()
        panel.activate()
        assert "Disconnect" in panel.notice.text() and not any(
            row["is_active_source"] for row in memory_repository["rows"]
        )
        panel.disconnect_device()
        wait_until(lambda: first.isFinished() and not panel.tasks)
        panel.table.selectRow(1)
        panel.connect_device()
        wait_until(
            lambda: panel.capture is not first and panel.capture.latest is not None
        )
        panel.activate()
        wait_until(
            lambda: (
                any(row["is_active_source"] for row in memory_repository["rows"])
                and not panel.tasks
            )
        )
    finally:
        panel.shutdown()
        if panel.capture:
            assert panel.capture.wait(1500)
        wait_until(lambda: not panel.tasks)
        panel.close()


def test_wizard_invalid_endpoint_does_not_save_and_valid_simulation_saves(
    memory_repository,
):
    wizard = hardware_ui.DeviceWizard(None, ADMIN)
    wizard.name.setText("Classroom camera")
    wizard.kind.setCurrentText("http")
    wizard.source.setText("http://169.254.169.254/latest/meta-data/")
    wizard.lan.setChecked(True)
    wizard.save()
    assert not memory_repository["saves"] and wizard.task is None
    assert "not an allowed" in wizard.notice.text()
    wizard.kind.setCurrentText("mock")
    wizard.save()
    wait_until(lambda: wizard.saved)
    assert wizard.result() == QDialog.DialogCode.Accepted
    assert memory_repository["saves"][0].source == "mock://classroom"


def test_wizard_does_not_persist_incomplete_authentication(memory_repository):
    wizard = hardware_ui.DeviceWizard(None, ADMIN)
    wizard.name.setText("Classroom camera")
    wizard.kind.setCurrentText("http")
    wizard.source.setText("http://10.0.0.5/stream")
    wizard.lan.setChecked(True)
    wizard.password.setText("synthetic-password")
    wizard.save()
    assert not memory_repository["saves"] and "username" in wizard.notice.text()
    wizard.password.clear()
    wizard.close()


def test_wizard_test_preview_uses_simulated_source_and_closes_worker(
    memory_repository, monkeypatch
):
    previews = []

    def run_preview(dialog):
        previews.append(dialog)
        dialog.show()
        wait_until(lambda: dialog.worker.latest is not None)
        dialog.render_preview()
        assert dialog.preview.image is not None
        dialog.reject()
        wait_until(lambda: dialog.worker.isFinished())
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(hardware_ui.PreviewDialog, "exec", run_preview)
    wizard = hardware_ui.DeviceWizard(None, ADMIN)
    wizard.name.setText("SIMULATED classroom")
    wizard.kind.setCurrentText("mock")
    wizard.test()
    assert previews and "SIMULATED" in wizard.notice.text()
    assert not previews[0].worker.isRunning()
    wizard.close()


def test_wizard_database_failure_is_actionable_and_allows_retry(
    memory_repository, monkeypatch
):
    def fail(*args, **kwargs):
        raise RuntimeError("private-driver-context")

    monkeypatch.setattr(devices, "save_device", fail)
    wizard = hardware_ui.DeviceWizard(None, ADMIN)
    wizard.name.setText("SIMULATED classroom")
    wizard.kind.setCurrentText("mock")
    wizard.save()
    wait_until(lambda: wizard.task is None)
    assert (
        not wizard.saved and wizard.save_button.isEnabled() and wizard.body.isEnabled()
    )
    assert (
        "Save failed" in wizard.notice.text() and "private" not in wizard.notice.text()
    )
    wizard.close()


def test_wizard_scrolls_at_supported_small_window_and_keeps_footer_visible(
    memory_repository,
):
    wizard = hardware_ui.DeviceWizard(None, ADMIN)
    wizard.setStyleSheet(STYLE)
    wizard.resize(710, 600)
    wizard.show()
    QApplication.processEvents()
    scroll = wizard.findChild(QScrollArea)
    assert wizard.height() <= 650
    assert scroll.horizontalScrollBar().maximum() == 0
    assert wizard.save_button.geometry().bottom() < wizard.height()
    assert wizard.save_button.isVisible()
    wizard.close()


@pytest.mark.parametrize(
    "width,height", [(950, 650), (1280, 720), (1366, 768), (1920, 1080)]
)
def test_hardware_panel_fits_role_workspace_at_supported_sizes(
    memory_repository, width, height
):
    panel = hardware_ui.HardwarePanel(ADMIN)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(panel)
    scroll.setStyleSheet(STYLE)
    # Match the existing main window's 220px sidebar and 62px header.
    scroll.resize(width - 220, height - 62)
    scroll.show()
    try:
        wait_until(lambda: not panel.tasks)
        QApplication.processEvents()
        assert scroll.horizontalScrollBar().maximum() == 0
        assert panel.preview.width() >= 320
    finally:
        panel.shutdown()
        wait_until(lambda: not panel.tasks)
        scroll.close()


def test_hardware_preview_uses_measured_fps_and_labels_low_rate(memory_repository):
    memory_repository["rows"].append(row_for(cameras.discover_simulated_devices()[0]))
    panel = hardware_ui.HardwarePanel(ADMIN)
    try:
        wait_until(lambda: bool(panel.rows) and not panel.tasks)
        panel.table.selectRow(0)
        panel.connect_device()
        wait_until(
            lambda: panel.capture is not None and panel.capture.latest is not None
        )
        panel.capture.info = dict(panel.capture.info, fps=3.5)
        panel.render_preview()
        assert (
            "3.5 FPS" in panel.diagnostics.text()
            and "Low frame rate" in panel.diagnostics.text()
        )
    finally:
        panel.shutdown()
        if panel.capture:
            assert panel.capture.wait(1500)
        wait_until(lambda: not panel.tasks)
        panel.close()
