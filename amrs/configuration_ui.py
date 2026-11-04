"""One-time, read-only Oracle connectivity setup using Windows encrypted storage."""

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import QCheckBox, QDialog, QGridLayout, QLabel, QVBoxLayout

from . import configuration
from .gui import BackgroundTask, action, field, form_cell, text_hint


class DatabaseSetup(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AMRS — Oracle connection setup")
        self.resize(620, 520)
        self.task = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        title = QLabel("Connect AMRS to Oracle")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)
        layout.addWidget(
            text_hint(
                "Use the separate runtime account provisioned by your DBA. This form verifies the current schema; it does not create users or run migrations."
            )
        )
        self.username = field("Oracle runtime username")
        self.schema = field("Schema owner, if different")
        self.dsn = field("localhost:1521/FREEPDB1")
        self.password = field("Runtime account password", True)
        grid = QGridLayout()
        for i, (label, widget) in enumerate(
            (
                ("Runtime account", self.username),
                ("Application schema", self.schema),
                ("Oracle service", self.dsn),
                ("Runtime password", self.password),
            )
        ):
            grid.addWidget(form_cell(label, widget), i, 0)
        layout.addLayout(grid)
        self.remember = QCheckBox("Remember securely for this Windows user")
        self.remember.setChecked(True)
        layout.addWidget(self.remember)
        self.notice = QLabel(
            "Credentials are encrypted using Windows DPAPI. Never use SYSTEM for the application runtime."
        )
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.save = action("Verify connection & continue", self.submit, "success")
        layout.addWidget(self.save)
        layout.addWidget(action("Close", self.reject))

    def submit(self):
        if self.task:
            return
        values = {
            "username": self.username.text(),
            "schema": self.schema.text(),
            "dsn": self.dsn.text(),
            "password": self.password.text(),
        }
        remember = self.remember.isChecked()
        try:
            configuration.validate(values)
        except ValueError as exc:
            self.notice.setText(str(exc))
            return
        self.save.setEnabled(False)
        self.notice.setText("Checking Oracle connectivity and migration state…")
        task = BackgroundTask(lambda: configuration.verify_and_save(values, remember))
        self.task = task

        def done(_):
            self.task = None
            self.password.clear()
            self.accept()

        def failed(exc):
            from .migrations.runner import MigrationError

            self.task = None
            self.save.setEnabled(True)
            self.notice.setText(
                str(exc)
                if isinstance(exc, (ValueError, MigrationError))
                else "Cannot connect. Check Oracle service, runtime credentials, permissions and schema setup."
            )

        task.signals.succeeded.connect(done, Qt.ConnectionType.QueuedConnection)
        task.signals.failed.connect(failed, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(task)

    def done(self, result):
        if self.task:
            self.notice.setText("Wait for the connection check to finish.")
            return
        super().done(result)
