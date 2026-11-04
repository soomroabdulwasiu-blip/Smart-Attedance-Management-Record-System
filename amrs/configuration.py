"""Explicit runtime-only Oracle setup. Never migrates or reads legacy batch files."""

import os
import re

from .secure_store import SecretStore


def validate(values):
    user = values.get("username", "").strip().upper()
    schema = values.get("schema", "").strip().upper()
    dsn = values.get("dsn", "").strip()
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,29}", user) or (
        schema and not re.fullmatch(r"[A-Z][A-Z0-9_]{0,29}", schema)
    ):
        raise ValueError("Enter simple Oracle runtime and owner/schema account names.")
    match = re.fullmatch(r"[A-Za-z0-9.-]+:(\d{1,5})/[A-Za-z0-9_.-]+", dsn)
    if not match or not 1 <= int(match[1]) <= 65535:
        raise ValueError(
            "Use an Oracle service address such as localhost:1521/FREEPDB1."
        )
    if not values.get("password"):
        raise ValueError("Enter the runtime account password.")
    return {
        "username": user,
        "schema": schema,
        "dsn": dsn,
        "password": values["password"],
    }


def install(values):
    values = validate(values)
    os.environ.update(
        AMRS_DB_USERNAME=values["username"],
        AMRS_DB_SCHEMA=values["schema"],
        AMRS_ORACLE_DSN=values["dsn"],
        AMRS_DB_PASSWORD=values["password"],
    )
    from . import db

    db.DSN = values["dsn"]


def load_runtime():
    if all(
        os.getenv(name)
        for name in ("AMRS_DB_USERNAME", "AMRS_ORACLE_DSN", "AMRS_DB_PASSWORD")
    ):
        return True
    saved = SecretStore("database").get("runtime")
    if saved:
        values = dict(saved)
        for key, env in (
            ("username", "AMRS_DB_USERNAME"),
            ("schema", "AMRS_DB_SCHEMA"),
            ("dsn", "AMRS_ORACLE_DSN"),
            ("password", "AMRS_DB_PASSWORD"),
        ):
            if env in os.environ:
                values[key] = os.environ[env]
        install(values)
        return True
    return False


def verify_and_save(values, remember=True):
    import oracledb

    from .migrations.runner import require_current

    values = validate(values)
    with oracledb.connect(
        user=values["username"],
        password=values["password"],
        dsn=values["dsn"],
        tcp_connect_timeout=5,
        retry_count=0,
    ) as connection:
        connection.call_timeout = 8000
        if values["schema"]:
            connection.cursor().execute(
                "ALTER SESSION SET CURRENT_SCHEMA=" + values["schema"]
            )
        require_current(connection)
    if remember:
        SecretStore("database").set("runtime", values)
    install(values)
