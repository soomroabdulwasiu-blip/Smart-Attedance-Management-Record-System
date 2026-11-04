"""Rotating, redacted diagnostics: no exception values, local variables or PII."""

import json
import logging
import logging.handlers
import os
import sys
import traceback
import uuid
import zipfile
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .paths import profile_root

LOG_DIR = Path(
    os.environ.get(
        "AMRS_LOG_DIR",
        profile_root() / "logs",
    )
)


def configure():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("amrs.safe")
    if not logger.handlers:
        handler = logging.handlers.RotatingFileHandler(
            LOG_DIR / "events.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    try:
        from .config import load

        logger.setLevel(load().log_level)
    except OSError, ValueError, TypeError:
        logger.setLevel(logging.INFO)
    return logger


def record(action, error=None, role=None):
    event_id = str(uuid.uuid4())
    item = {
        "id": event_id,
        "time": datetime.now(UTC).isoformat(),
        "action": action,
        "role": role,
    }
    if error is not None:
        item["exception_type"] = type(error).__name__
        item["stack"] = [
            {
                "module": Path(frame.filename).name,
                "line": frame.lineno,
                "function": frame.name,
            }
            for frame in traceback.extract_tb(error.__traceback__)
        ]
    logger = configure()
    if error is None:
        logger.info(json.dumps(item))
    else:
        logger.error(json.dumps(item))
    return event_id


def install_exception_hook():
    def hook(kind, error, tb):
        event_id = record("UNHANDLED_EXCEPTION", error)
        from PySide6.QtWidgets import QApplication, QMessageBox

        if QApplication.instance():
            QMessageBox.warning(
                None,
                "AMRS",
                "An unexpected error occurred. Reference: "
                + event_id
                + "\nExport diagnostics for the administrator. No password or face data is included.",
            )

    sys.excepthook = hook


def export(path):
    result: dict = {
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "packages": {},
    }
    for name in (
        "PySide6-Essentials",
        "opencv-python",
        "oracledb",
        "numpy",
        "bcrypt",
        "Flask",
        "requests",
    ):
        try:
            result["packages"][name] = version(name)
        except PackageNotFoundError:
            result["packages"][name] = "not installed"
    # No config/vault/database/biometric files are included.
    with zipfile.ZipFile(path, "x", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("versions.json", json.dumps(result, indent=2))
        for file in LOG_DIR.glob("events.log*"):
            if file.is_file() and not file.is_symlink():
                archive.write(file, "logs/" + file.name)
    return path
