"""Real camera management: Oracle configuration and background capture workers."""

import threading
import uuid

import cv2
from PySide6.QtCore import Qt, QThread, QThreadPool, QTimer, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from . import cameras, devices
from .gui import (
    BackgroundTask,
    CameraPreview,
    action,
    field,
    fill,
    form_cell,
    table,
    text_hint,
)


class CaptureTask(QThread):
    status = Signal(str)
    connected = Signal(object)

    def __init__(self, factory, parent=None):
        super().__init__(parent)
        self.factory = factory
        self.cancel = threading.Event()
        self.latest = None
        self.info = None
        self.last_error = ""

    def run(self):
        adapter = None
        try:
            adapter = self.factory()
            self.status.emit("Connecting…")
            if not adapter.connect():
                self.last_error = (
                    adapter.get_connection_status()["last_error"]
                    or "Camera connection was not established."
                )
                self.status.emit(self.last_error)
                return
            self.info = adapter.get_device_info()
            self.connected.emit(self.info)
            self.status.emit(
                "Connected — preview only; attendance is not being marked."
            )
            while not self.cancel.is_set():
                ok, frame = adapter.read_frame()
                if not ok:
                    self.latest = None
                    self.status.emit(
                        "Stream interrupted. Reconnecting within the configured retry limit…"
                    )
                    if not adapter.reconnect(self.cancel):
                        if not self.cancel.is_set():
                            self.last_error = (
                                adapter.get_connection_status()["last_error"]
                                or "Camera reconnect limit reached."
                            )
                            self.status.emit(self.last_error)
                        return
                    self.info = adapter.get_device_info()
                    self.connected.emit(self.info)
                    continue
                self.latest = frame
                self.info = adapter.get_device_info()
                self.cancel.wait(0.04)
        except Exception:  # noqa: BLE001 - sanitize native capture and secret-store failures
            self.last_error = "Connection failed. Check the source, access permissions, credentials and stream format."
            self.status.emit(self.last_error)
        finally:
            if adapter is not None:
                adapter.release()
            self.latest = None

    def request_stop(self):
        self.cancel.set()


class AsyncPanel(QWidget):
    """All Oracle/network actions snapshot inputs before entering a worker."""

    def __init__(self, user, parent=None):
        super().__init__(parent)
        self.user = user
        self.tasks = set()
        self.notice = QLabel("")
        self.notice.setObjectName("helperText")
        self.notice.setWordWrap(True)

    def submit(self, fn, done=None):
        task = BackgroundTask(fn)
        self.tasks.add(task)
        self.notice.setText("Working…")

        def succeeded(result):
            self.tasks.discard(task)
            self.notice.setText("Completed successfully.")
            if done is not None:
                done(result)

        def failed(exc):
            self.tasks.discard(task)
            from .migrations.runner import MigrationError

            self.notice.setText(
                str(exc)
                if isinstance(exc, (ValueError, MigrationError))
                else "Operation failed. Check Oracle connectivity and setup; retry after resolving the problem."
            )

        task.signals.succeeded.connect(succeeded, Qt.ConnectionType.QueuedConnection)
        task.signals.failed.connect(failed, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(task)


class PreviewDialog(QDialog):
    def __init__(self, parent, factory, on_connected=None):
        super().__init__(parent)
        self.setWindowTitle("Camera connection test — preview only")
        self.resize(900, 650)
        layout = QVBoxLayout(self)
        self.preview = CameraPreview()
        layout.addWidget(self.preview, 1)
        self.status = QLabel("Connecting…")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        layout.addWidget(action("Close preview", self.reject))
        self.worker = CaptureTask(factory, self)
        self.worker.status.connect(self.status.setText)
        if on_connected:
            self.worker.connected.connect(on_connected)
        self.timer = QTimer(self)
        self.timer.setInterval(80)
        self.timer.timeout.connect(self.render_preview)
        self.timer.start()
        self.worker.finished.connect(self.stopped)
        self.closing = False
        self.worker.start()

    def render_preview(self):
        if self.worker.latest is not None:
            self.preview.setImage(frame_image(self.worker.latest))

    def stopped(self):
        self.timer.stop()
        if self.closing:
            self.reject()

    def done(self, result):
        if self.worker.isRunning():
            self.closing = True
            self.worker.request_stop()
            self.status.setText("Closing camera safely…")
            return
        super().done(result)

    def closeEvent(self, event):
        if self.worker.isRunning():
            self.closing = True
            self.worker.request_stop()
            event.ignore()
            return
        super().closeEvent(event)


def frame_image(frame):
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    return QImage(rgb.data, w, h, rgb.strides[0], QImage.Format.Format_RGB888).copy()


class DeviceWizard(QDialog):
    def __init__(self, parent, user, row=None):
        super().__init__(parent)
        self.user = user
        self.device_id = row["device_id"] if row else str(uuid.uuid4())
        self.saved = False
        self.task = None
        self.preview_dialog = None
        self.setWindowTitle("Edit camera" if row else "Add a camera")
        self.resize(710, 600)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.body = QWidget()
        layout = QVBoxLayout(self.body)
        layout.setContentsMargins(12, 12, 12, 12)
        scroll.setWidget(self.body)
        outer.addWidget(scroll, 1)
        title = QLabel("Connect your classroom camera")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)
        layout.addWidget(
            text_hint(
                "1. Choose source   →   2. Test and preview   →   3. Save   →   4. Select for attendance"
            )
        )
        self.name = field("e.g. Room A — USB webcam")
        self.kind = QComboBox()
        self.kind.addItems(cameras.DEVICE_TYPES)
        self.source = field("Camera index or a numeric-IP streaming URL")
        self.lan = QCheckBox("Allow access to this specific LAN camera")
        self.enabled = QCheckBox("Enable this device")
        self.enabled.setChecked(True)
        self.profile = QComboBox()
        self.profile.addItems(cameras.SIMULATION_PROFILES)
        self.open_ms = QSpinBox()
        self.open_ms.setRange(250, 15000)
        self.open_ms.setValue(5000)
        self.read_ms = QSpinBox()
        self.read_ms.setRange(250, 10000)
        self.read_ms.setValue(3000)
        self.retries = QSpinBox()
        self.retries.setRange(0, 5)
        self.retries.setValue(2)
        self.username = field("Camera username (optional)")
        self.password = field("New camera password (leave blank to keep)", True)
        self.auth_mode = QComboBox()
        self.auth_mode.addItems(["digest", "basic"])
        self.clear_credentials = QCheckBox("Remove saved credentials")
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)
        for i, (label, widget) in enumerate(
            (
                ("Device name", self.name),
                ("Device type", self.kind),
                ("Camera index / endpoint", self.source),
                ("Simulation scenario", self.profile),
                ("Open timeout (ms)", self.open_ms),
                ("Read timeout (ms)", self.read_ms),
                ("Reconnect attempts", self.retries),
                ("HTTP authentication", self.auth_mode),
                ("Camera username", self.username),
                ("Camera password", self.password),
            )
        ):
            grid.addWidget(form_cell(label, widget), i // 2, i % 2)
        layout.addLayout(grid)
        layout.addWidget(self.lan)
        layout.addWidget(self.enabled)
        layout.addWidget(self.clear_credentials)
        self.notice = QLabel(
            "Simulation creates synthetic shapes, not real student faces. Camera secrets are encrypted for this Windows user."
        )
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        buttons = QHBoxLayout()
        self.test_button = action("Test & preview", self.test)
        buttons.addWidget(self.test_button)
        buttons.addWidget(action("Cancel", self.reject))
        self.save_button = action("Save camera", self.save, "success")
        buttons.addWidget(self.save_button)
        outer.addLayout(buttons)
        self.kind.currentTextChanged.connect(self.kind_changed)
        if row:
            cfg = devices.config_from_row(row)
            self.name.setText(cfg.name)
            self.kind.setCurrentText(cfg.device_type)
            self.source.setText(str(cfg.source))
            self.lan.setChecked(cfg.allow_private_network)
            self.profile.setCurrentText(cfg.simulation_profile)
            self.open_ms.setValue(cfg.open_timeout_ms)
            self.read_ms.setValue(cfg.read_timeout_ms)
            self.retries.setValue(cfg.reconnect_attempts)
            self.enabled.setChecked(bool(row["enabled"]))
        else:
            self.kind_changed(self.kind.currentText())

    def kind_changed(self, kind):
        self.profile.setEnabled(kind == "mock")
        if kind == "mock":
            self.source.setText("mock://classroom")
            self.name.setPlaceholderText("SIMULATED classroom camera")
        elif kind in ("builtin", "usb"):
            self.source.setText("0")
        else:
            self.source.clear()

    def configuration(self):
        return cameras.validate_config(
            cameras.CameraConfig(
                self.device_id,
                self.name.text(),
                self.kind.currentText(),
                self.source.text(),
                self.lan.isChecked(),
                self.open_ms.value(),
                self.read_ms.value(),
                self.retries.value(),
                250,
                self.profile.currentText(),
            )
        )

    def credentials(self):
        if self.clear_credentials.isChecked():
            return {}
        if self.password.text():
            if not self.username.text().strip():
                raise ValueError("Enter a camera username with the new password.")
            if not self.source.text().strip().startswith(("http://", "https://")):
                raise ValueError(
                    "Saved authentication is supported for HTTP/HTTPS camera streams. Use a protected gateway for authenticated RTSP."
                )
            return {
                "username": self.username.text().strip(),
                "password": self.password.text(),
                "mode": self.auth_mode.currentText(),
            }
        return None

    def test(self):
        try:
            config = self.configuration()
            credentials = self.credentials()

            def factory():
                if credentials is None:
                    from .secure_store import SecretStore

                    secret = SecretStore().get(config.device_id)
                else:
                    secret = credentials
                return cameras.create_adapter(config, credentials=secret)

            self.preview_dialog = PreviewDialog(
                self,
                factory,
                lambda info: self.notice.setText(
                    "Connected"
                    + (" — SIMULATED" if info["simulated"] else "")
                    + ". Close the preview, then save the configuration."
                ),
            )
            self.preview_dialog.exec()
        except ValueError as exc:
            self.notice.setText(str(exc))

    def save(self):
        if self.task is not None:
            return
        try:
            config = self.configuration()
            credentials = self.credentials()
            enabled = self.enabled.isChecked()
        except ValueError as exc:
            self.notice.setText(str(exc))
            return
        self.save_button.setEnabled(False)
        self.test_button.setEnabled(False)
        self.body.setEnabled(False)
        self.notice.setText("Saving encrypted credentials and Oracle configuration…")
        task = BackgroundTask(
            lambda: devices.save_device(self.user, config, enabled, credentials)
        )
        self.task = task

        def done(_):
            self.task = None
            self.saved = True
            self.password.clear()
            self.accept()

        def failed(exc):
            self.task = None
            self.save_button.setEnabled(True)
            self.test_button.setEnabled(True)
            self.body.setEnabled(True)
            self.notice.setText(
                str(exc)
                if isinstance(exc, ValueError)
                else "Save failed. Check database connectivity and migrations."
            )

        task.signals.succeeded.connect(done, Qt.ConnectionType.QueuedConnection)
        task.signals.failed.connect(failed, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(task)

    def done(self, result):
        if self.task is not None:
            self.notice.setText("Wait for the save operation to finish.")
            return
        super().done(result)


class HardwarePanel(AsyncPanel):
    def __init__(self, user, parent=None):
        super().__init__(user, parent)
        self.rows = []
        self.capture = None
        self.capture_device = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(
            text_hint(
                "Manage saved sources here. Teachers use enabled devices through the same face-attendance pipeline. Status is last observed, not proof that an idle device is online."
            )
        )
        grid = QGridLayout()
        for i, (text, fn) in enumerate(
            (
                ("Add device", self.add),
                ("Discover local cameras", self.discover),
                ("Add simulated cameras", self.simulate),
                ("Refresh devices", self.refresh),
            )
        ):
            grid.addWidget(action(text, fn), i // 2, i % 2)
        layout.addLayout(grid)
        self.table = table(
            ["Camera", "Type", "Enabled", "Selected", "Last status", "Last connected"]
        )
        self.table.setMinimumHeight(200)
        layout.addWidget(self.table)
        controls = QGridLayout()
        for i, (text, fn) in enumerate(
            (
                ("Connect / live preview", self.connect_device),
                ("Disconnect", self.disconnect_device),
                ("Reconnect", self.reconnect_device),
                ("Select for attendance", self.activate),
                ("Edit configuration", self.edit),
                ("Remove device", self.remove),
            )
        ):
            controls.addWidget(action(text, fn), i // 2, i % 2)
        layout.addLayout(controls)
        self.preview = CameraPreview()
        layout.addWidget(self.preview, 1)
        self.diagnostics = QLabel("No camera connection has been tested.")
        self.diagnostics.setObjectName("helperText")
        self.diagnostics.setWordWrap(True)
        layout.addWidget(self.diagnostics)
        layout.addWidget(self.notice)
        self.timer = QTimer(self)
        self.timer.setInterval(80)
        self.timer.timeout.connect(self.render_preview)
        self.refresh()

    def selected(self):
        i = self.table.currentRow()
        if not 0 <= i < len(self.rows):
            raise ValueError("Select a saved camera first.")
        return self.rows[i]

    def refresh(self):
        self.submit(lambda: devices.list_devices(self.user), self.display)

    def display(self, rows):
        self.rows = rows
        shown = [
            dict(
                r,
                name=(
                    "SIMULATED — " + r["name"]
                    if r["device_type"] == "mock"
                    and not r["name"].startswith("SIMULATED")
                    else r["name"]
                ),
                enabled_text="Yes" if r["enabled"] else "No",
                active_text="Active source" if r["is_active_source"] else "—",
            )
            for r in rows
        ]
        fill(
            self.table,
            shown,
            [
                "name",
                "device_type",
                "enabled_text",
                "active_text",
                "status",
                "last_connected",
            ],
        )
        self.notice.setText(
            f"{len(rows)} saved camera(s)."
            if rows
            else "No saved cameras. Add a laptop/USB source or a clearly labelled simulation."
        )

    def add(self):
        dialog = DeviceWizard(self, self.user)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def edit(self):
        try:
            row = self.selected()
            if self.capture and self.capture.isRunning():
                raise ValueError("Disconnect the preview before editing a device.")
            dialog = DeviceWizard(self, self.user, row)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.refresh()
        except ValueError as exc:
            self.notice.setText(str(exc))

    def discover(self):
        def done(configs):
            self.notice.setText(
                f"Found {len(configs)} compatible local camera index(es). Choose Add device to review and save one."
            )
            QMessageBox.information(
                self,
                "Available cameras",
                "\n".join(c.name + " — index " + str(c.source) for c in configs)
                or "No compatible local cameras found. Check Windows camera permissions and close other camera apps.",
            )

        self.submit(lambda: cameras.discover_devices(max_devices=4), done)

    def simulate(self):
        def save():
            existing = devices.list_devices(self.user)
            for config in cameras.discover_simulated_devices():
                if not any(r["device_id"] == config.device_id for r in existing):
                    devices.save_device(self.user, config)

        self.submit(save, lambda _: self.refresh())

    def connect_device(self):
        try:
            row = self.selected()
            if self.capture and self.capture.isRunning():
                raise ValueError(
                    "Disconnect the current preview before switching cameras."
                )
            if not row["enabled"]:
                raise ValueError("Enable this camera before connecting.")
            device_id = row["device_id"]
            self.capture_device = device_id
            worker = CaptureTask(
                lambda: devices.adapter_for(self.user, device_id), self
            )
            self.capture = worker
            worker.status.connect(
                lambda message: (
                    self.notice.setText(message) if self.capture is worker else None
                )
            )
            worker.connected.connect(
                lambda info: self.connected(info, worker, device_id)
            )
            worker.finished.connect(lambda: self.capture_stopped(worker, device_id))
            self.capture.start()
            self.timer.start()
        except ValueError as exc:
            self.notice.setText(str(exc))

    def connected(self, info, worker=None, device_id=None):
        if worker is not None and self.capture is not worker:
            return
        prefix = "SIMULATED DEVICE — " if info["simulated"] else ""
        self.diagnostics.setText(
            prefix
            + "Protocol: "
            + str(info["protocol"])
            + "  •  Resolution/FPS measured after frames arrive. No manufacturer metadata is inferred."
        )
        device_id = device_id or self.capture_device
        self.submit(
            lambda: devices.record_status(
                self.user, device_id, "CONNECTED", connected=True
            )
        )

    def render_preview(self):
        if self.capture and self.capture.latest is not None:
            frame = self.capture.latest
            self.preview.setImage(frame_image(frame))
            h, w = frame.shape[:2]
            info = self.capture.info or {}
            fps = info.get("fps")
            rate = (
                f" • Measured delivery: {fps:.1f} FPS"
                if isinstance(fps, (float, int))
                else " • Measuring frame delivery…"
            )
            if isinstance(fps, (float, int)) and fps < 8:
                rate += " • Low frame rate"
            self.diagnostics.setText(
                ("SIMULATED — " if info.get("simulated") else "")
                + f"Frame resolution: {w} × {h}"
                + rate
                + ". Preview does not mark attendance."
            )

    def capture_stopped(self, worker=None, device_id=None):
        worker = worker or self.capture
        device_id = device_id or self.capture_device
        if worker is None:
            return
        error = worker.last_error
        if self.capture is worker:
            self.timer.stop()
            self.preview.setImage(None)
            self.diagnostics.setText(
                "Connection error: " + error
                if error
                else "Camera disconnected. No stream is being captured."
            )
        self.submit(
            lambda: devices.record_status(
                self.user, device_id, "ERROR" if error else "DISCONNECTED", error=error
            ),
            lambda _: self.refresh(),
        )

    def disconnect_device(self):
        if self.capture and self.capture.isRunning():
            self.capture.request_stop()
            self.notice.setText("Disconnecting safely…")

    def reconnect_device(self):
        if self.capture and self.capture.isRunning():
            self.notice.setText("Disconnect first, then reconnect.")
            return
        self.connect_device()

    def activate(self):
        try:
            device_id = self.selected()["device_id"]
            if (
                self.capture
                and self.capture.isRunning()
                and device_id != self.capture_device
            ):
                raise ValueError(
                    "Disconnect the preview before changing the active camera."
                )
        except ValueError as exc:
            self.notice.setText(str(exc))
            return
        self.submit(
            lambda: devices.select_active(self.user, device_id),
            lambda _: self.refresh(),
        )

    def remove(self):
        try:
            if self.capture and self.capture.isRunning():
                raise ValueError("Disconnect the preview before removing a camera.")
            row = self.selected()
        except ValueError as exc:
            self.notice.setText(str(exc))
            return
        if (
            QMessageBox.question(
                self,
                "Remove camera",
                "Remove this saved camera configuration and its encrypted credentials? Attendance records will be preserved.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.submit(
            lambda: devices.remove_device(self.user, row["device_id"]),
            lambda _: self.refresh(),
        )

    def shutdown(self):
        self.disconnect_device()
        return not (self.capture and self.capture.isRunning())
