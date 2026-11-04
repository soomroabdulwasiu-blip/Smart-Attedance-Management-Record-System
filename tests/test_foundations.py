"""Boundary tests for startup, encrypted secrets and non-destructive maintenance."""

import json
import time
import zipfile

import pytest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QDialog

from amrs import config, configuration, diagnostics, maintenance, secure_store
from amrs.configuration_ui import DatabaseSetup


def test_environment_precedence_and_no_secret_in_plain_settings(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"pool_max": 8, "face_threshold": 0.7}))
    monkeypatch.setenv("AMRS_POOL_MAX", "9")
    settings = config.load(path)
    assert settings.pool_max == 9 and settings.face_threshold == 0.7
    path.write_text(json.dumps({"password": "must-not-be-accepted"}))
    with pytest.raises(ValueError, match="unsupported"):
        config.load(path)
    saved = {
        "username": "SAVED",
        "schema": "OWNER",
        "dsn": "localhost:1521/FREEPDB1",
        "password": "synthetic-vault-only",
    }

    class Vault:
        def get(self, key):
            return saved

    captured = []
    monkeypatch.setattr(configuration, "SecretStore", lambda *args: Vault())
    monkeypatch.setattr(configuration, "install", captured.append)
    monkeypatch.delenv("AMRS_DB_PASSWORD", raising=False)
    monkeypatch.setenv("AMRS_DB_USERNAME", "OVERRIDE")
    assert (
        configuration.load_runtime()
        and captured[0]["username"] == "OVERRIDE"
        and captured[0]["password"] == "synthetic-vault-only"
    )


@pytest.mark.parametrize(
    "values",
    [
        {"pool_min": 10, "pool_max": 2},
        {"qr_port": 0},
        {"face_threshold": "nan"},
        {"face_margin": 2},
        {"locale": "invented"},
        {"qr_cert_file": "cert-without-key"},
    ],
)
def test_invalid_config_is_actionable(tmp_path, monkeypatch, values):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(values))
    for name in (
        "AMRS_POOL_MIN",
        "AMRS_POOL_MAX",
        "AMRS_FACE_THRESHOLD",
        "AMRS_FACE_MARGIN",
        "AMRS_QR_PORT",
        "AMRS_QR_CERT_FILE",
        "AMRS_QR_KEY_FILE",
        "AMRS_LOCALE",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValueError):
        config.load(path)


def test_encrypted_store_roundtrip_removal_and_tampering(tmp_path):
    store = secure_store.SecretStore("camera", tmp_path)
    value = {"username": "synthetic", "password": "sensitive-test-value"}
    store.set("test", value)
    assert store.get("test") == value
    assert b"sensitive-test-value" not in store.path.read_bytes()
    store.set("test", None)
    assert store.get("test") is None
    store.path.write_text("{broken")
    with pytest.raises(ValueError, match="cannot be opened"):
        store.get("test")


def test_diagnostics_redacts_exception_values_and_exports_only_safe_files(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(diagnostics, "LOG_DIR", tmp_path / "logs")
    import logging

    logger = logging.getLogger("amrs.safe")
    old = list(logger.handlers)
    logger.handlers = []
    try:
        try:
            raise ValueError("DO_NOT_LOG_PASSWORD_OR_STUDENT_NAME")
        except ValueError as exc:
            event_id = diagnostics.record("TEST_OPERATION", exc, "ADMIN")
        file = diagnostics.LOG_DIR / "events.log"
        text = file.read_text()
        assert event_id in text and "ValueError" in text and "DO_NOT_LOG" not in text
        result = tmp_path / "diagnostics.zip"
        diagnostics.export(result)
        with zipfile.ZipFile(result) as archive:
            assert set(archive.namelist()) == {"versions.json", "logs/events.log"}
            assert "password" not in archive.read("versions.json").decode().lower()
    finally:
        for handler in logger.handlers:
            handler.close()
        logger.handlers = old


def test_maintenance_default_only_reads_and_missing_approval_never_writes(monkeypatch):
    seen = []

    def rows(sql, *args):
        seen.append(sql)
        return []

    def one(sql, *args):
        seen.append(sql)
        return {"n": 0} if "COUNT" in sql else {"schema_name": "SYNTHETIC"}

    monkeypatch.setattr(maintenance.db, "rows", rows)
    monkeypatch.setattr(maintenance.db, "one", one)
    result = maintenance.purge_inactive_records()
    assert result["counts"] == {"students": 0, "teachers": 0, "courses": 0} and all(
        sql.startswith("SELECT") for sql in seen
    )
    from amrs import devices

    monkeypatch.setattr(devices, "authorize", lambda user: None)
    monkeypatch.setattr(
        maintenance.db,
        "connection",
        lambda: pytest.fail("No transaction may start without valid approval"),
    )
    with pytest.raises(ValueError, match="approval"):
        maintenance.purge_inactive_records(confirm=True, user={"role": "ADMIN"})


def test_maintenance_rejects_wrong_or_expired_approval():
    with pytest.raises(ValueError):
        maintenance.validate_approval({"approved": True}, {"target": "synthetic"})


def test_connection_setup_validates_and_refuses_missing_migrations(monkeypatch):
    values = {
        "username": "runtime",
        "schema": "owner",
        "dsn": "localhost:1521/FREEPDB1",
        "password": "synthetic-only",
    }
    assert configuration.validate(values)["username"] == "RUNTIME"
    for invalid in (
        {**values, "schema": "OWNER; DROP TABLE X"},
        {**values, "dsn": "user:password@remote"},
        {**values, "password": ""},
    ):
        with pytest.raises(ValueError):
            configuration.validate(invalid)

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def cursor(self):
            return self

        def execute(self, *args):
            pass

    import oracledb

    from amrs.migrations import runner

    monkeypatch.setattr(oracledb, "connect", lambda **kwargs: Connection())
    monkeypatch.setattr(
        runner,
        "require_current",
        lambda conn: (_ for _ in ()).throw(runner.MigrationError("migration needed")),
    )
    monkeypatch.setattr(
        configuration,
        "install",
        lambda *args: pytest.fail("Invalid schemas cannot be installed"),
    )
    with pytest.raises(runner.MigrationError):
        configuration.verify_and_save(values, False)


def test_connection_form_does_not_block_ui(monkeypatch):
    events = []

    def slow(*args):
        time.sleep(0.25)

    monkeypatch.setattr(configuration, "verify_and_save", slow)
    form = DatabaseSetup()
    form.username.setText("RUNTIME")
    form.schema.setText("OWNER")
    form.dsn.setText("localhost:1521/FREEPDB1")
    form.password.setText("synthetic-only")
    form.show()
    form.submit()
    assert form.task is not None and not form.save.isEnabled()
    QTimer.singleShot(50, lambda: events.append("heartbeat"))
    loop = QEventLoop()
    QTimer.singleShot(800, loop.quit)
    loop.exec()
    assert (
        events == ["heartbeat"]
        and form.result() == QDialog.DialogCode.Accepted
        and not form.password.text()
    )
