"""Authorized Oracle camera configuration, independent of Qt and capture."""

import json
from dataclasses import asdict

from . import db
from .secure_store import SecretStore

CONFIG_FIELDS = (
    "allow_private_network",
    "open_timeout_ms",
    "read_timeout_ms",
    "reconnect_attempts",
    "retry_delay_ms",
    "simulation_profile",
)


def authorize(user, roles=("ADMIN",)):
    db.require_actor(user, roles)
    if not db.session_is_active(user):
        raise ValueError("Your account is no longer active. Sign in again.")


def list_devices(user):
    authorize(user, ("ADMIN", "TEACHER"))
    return db.rows(
        "SELECT device_id,name,device_type,endpoint,enabled,is_active_source,config_json,status,last_error,last_connected,created_at,updated_at FROM camera_devices"
        + (" WHERE enabled=1" if user["role"] == "TEACHER" else "")
        + " ORDER BY name"
    )


def config_from_row(row):
    from .cameras import CameraConfig, validate_config

    values = json.loads(row.get("config_json") or "{}")
    return validate_config(
        CameraConfig(
            device_id=row["device_id"],
            name=row["name"],
            device_type=row["device_type"],
            source=row["endpoint"],
            **{key: values[key] for key in CONFIG_FIELDS if key in values},
        )
    )


def save_device(user, config, enabled=True, credentials=None):
    from .cameras import validate_config

    authorize(user)
    config = validate_config(config)
    values = asdict(config)
    options = json.dumps({key: values[key] for key in CONFIG_FIELDS if key in values})
    if len(options) > 4000:
        raise ValueError("Device configuration is too large.")
    vault = SecretStore()
    previous = vault.get(config.device_id) if credentials is not None else None
    if credentials is not None:
        vault.set(config.device_id, credentials or None)
    try:
        with db.connection() as connection:
            cur = connection.cursor()
            cur.execute(
                "MERGE INTO camera_devices d USING (SELECT :id device_id FROM dual) x ON (d.device_id=x.device_id) WHEN MATCHED THEN UPDATE SET name=:name,device_type=:kind,endpoint=:endpoint,enabled=:enabled,is_active_source=CASE WHEN :enabled=0 THEN 0 ELSE is_active_source END,config_json=:config,updated_at=CURRENT_TIMESTAMP WHEN NOT MATCHED THEN INSERT(device_id,name,device_type,endpoint,enabled,config_json,created_by) VALUES(:id,:name,:kind,:endpoint,:enabled,:config,:actor)",
                {
                    "id": config.device_id,
                    "name": config.name,
                    "kind": config.device_type,
                    "endpoint": str(config.source),
                    "enabled": int(enabled),
                    "config": options,
                    "actor": user["user_id"],
                },
            )
            if not enabled:
                cur.execute(
                    "UPDATE camera_devices SET is_active_source=0 WHERE device_id=:id",
                    {"id": config.device_id},
                )
            db.audit_event(cur, user, "DEVICE_SAVED", config.device_id)
    except Exception:
        if credentials is not None:
            vault.set(config.device_id, previous)
        raise
    return config.device_id


def select_active(user, device_id):
    authorize(user)
    with db.connection() as connection:
        cur = connection.cursor()
        cur.execute(
            "SELECT device_id FROM camera_devices WHERE device_id=:id AND enabled=1 FOR UPDATE",
            {"id": device_id},
        )
        if not cur.fetchone():
            raise ValueError("Choose an enabled saved camera.")
        cur.execute(
            "UPDATE camera_devices SET is_active_source=0 WHERE is_active_source=1"
        )
        cur.execute(
            "UPDATE camera_devices SET is_active_source=1,updated_at=CURRENT_TIMESTAMP WHERE device_id=:id",
            {"id": device_id},
        )
        db.audit_event(cur, user, "DEVICE_SELECTED", device_id)


def remove_device(user, device_id):
    authorize(user)
    with db.connection() as connection:
        cur = connection.cursor()
        cur.execute("DELETE FROM camera_devices WHERE device_id=:id", {"id": device_id})
        if cur.rowcount != 1:
            raise ValueError("Device no longer exists.")
        db.audit_event(cur, user, "DEVICE_REMOVED", device_id)
    # A stale encrypted credential after a filesystem error cannot reconnect a deleted device.
    SecretStore().set(device_id, None)


def record_status(user, device_id, state, error="", connected=False):
    authorize(user)
    if state not in (
        "CONNECTED",
        "DISCONNECTED",
        "ERROR",
        "CONNECTING",
        "RECONNECTING",
    ):
        raise ValueError("Invalid device status.")
    with db.connection() as connection:
        cur = connection.cursor()
        cur.execute(
            "UPDATE camera_devices SET status=:state,last_error=:error,last_connected=CASE WHEN :connected=1 THEN CURRENT_TIMESTAMP ELSE last_connected END,updated_at=CURRENT_TIMESTAMP WHERE device_id=:id",
            {
                "state": state,
                "error": "Connection failed; check the device diagnostics."
                if error
                else None,
                "connected": int(connected),
                "id": device_id,
            },
        )
        db.audit_event(cur, user, "DEVICE_" + state, device_id)


def adapter_for(user, device_id):
    from .cameras import create_adapter

    rows = list_devices(user)
    row = next(
        (item for item in rows if item["device_id"] == device_id and item["enabled"]),
        None,
    )
    if row is None:
        raise ValueError("This camera is disabled or unavailable.")
    return create_adapter(
        config_from_row(row), credentials=SecretStore().get(device_id)
    )


def active_device(user):
    return next((row for row in list_devices(user) if row["is_active_source"]), None)
