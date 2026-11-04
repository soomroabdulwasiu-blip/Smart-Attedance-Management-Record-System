"""Validated non-secret settings: environment, per-user JSON, then defaults."""

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .paths import profile_root


@dataclass(frozen=True)
class Settings:
    db_dsn: str = "localhost:1521/FREEPDB1"
    db_username: str = "AMRS"
    db_schema: str = ""
    pool_min: int = 1
    pool_max: int = 5
    face_threshold: float = 0.55
    face_margin: float = 0.08
    qr_port: int = 8090
    qr_public_host: str = ""
    qr_cert_file: str = ""
    qr_key_file: str = ""
    smtp_provider: str = "gmail"
    locale: str = "en"
    log_level: str = "INFO"


def load(path=None):
    default = profile_root() / "config.json"
    path = Path(path or os.environ.get("AMRS_CONFIG_FILE", default))
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(data, dict) or set(data) - set(Settings.__dataclass_fields__):
        raise ValueError("Non-secret application settings contain unsupported fields.")
    env = {
        "db_dsn": "AMRS_ORACLE_DSN",
        "db_username": "AMRS_DB_USERNAME",
        "db_schema": "AMRS_DB_SCHEMA",
        "pool_min": "AMRS_POOL_MIN",
        "pool_max": "AMRS_POOL_MAX",
        "face_threshold": "AMRS_FACE_THRESHOLD",
        "face_margin": "AMRS_FACE_MARGIN",
        "qr_port": "AMRS_QR_PORT",
        "qr_public_host": "AMRS_QR_PUBLIC_HOST",
        "qr_cert_file": "AMRS_QR_CERT_FILE",
        "qr_key_file": "AMRS_QR_KEY_FILE",
        "locale": "AMRS_LOCALE",
        "log_level": "AMRS_LOG_LEVEL",
    }
    for field, key in env.items():
        if key in os.environ:
            data[field] = os.environ[key]
    for field in ("pool_min", "pool_max", "qr_port"):
        if field in data:
            data[field] = int(data[field])
    for field in ("face_threshold", "face_margin"):
        if field in data:
            data[field] = float(data[field])
    result = Settings(**data)
    if (
        not 1 <= result.pool_min <= result.pool_max <= 30
        or not 1024 <= result.qr_port <= 65535
        or not 0 < result.face_threshold <= 1
        or not 0 <= result.face_margin < 1
    ):
        raise ValueError(
            "Pool, face threshold or QR settings are outside supported limits."
        )
    if (
        result.locale != "en"
        or result.smtp_provider != "gmail"
        or result.log_level not in ("DEBUG", "INFO", "WARNING", "ERROR")
    ):
        raise ValueError(
            "Choose English, Gmail and a supported log level for this release."
        )
    if bool(result.qr_cert_file) != bool(result.qr_key_file):
        raise ValueError("Configure both QR TLS certificate and key.")
    return result


def save_qr_tls(host, cert, key):
    """Update only the QR settings in the current Windows profile."""
    if any(
        os.getenv(name) is not None
        for name in ("AMRS_QR_PUBLIC_HOST", "AMRS_QR_CERT_FILE", "AMRS_QR_KEY_FILE")
    ):
        raise ValueError("QR settings are controlled by environment variables.")
    path = Path(os.environ.get("AMRS_CONFIG_FILE", profile_root() / "config.json"))
    load(path)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data.update(qr_public_host=host, qr_cert_file=str(cert), qr_key_file=str(key))
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=path.parent, delete=False, mode="w", encoding="utf-8"
    ) as f:
        temporary = Path(f.name)
        json.dump(data, f, indent=2)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
