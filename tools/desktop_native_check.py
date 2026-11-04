"""Disposable native Oracle setup for visible Windows desktop verification only."""

import json
import os
import secrets
import subprocess
import sys
import uuid
from pathlib import Path

from tools.native_oracle_check import admin


def main():
    if os.getenv("AMRS_ALLOW_NATIVE_ISOLATED_TEST") != "1":
        raise RuntimeError("Explicit isolated-test authorization required.")
    tag = uuid.uuid4().hex[:10].upper()
    owner = "AMRST_M_" + tag
    runtime = "AMRST_R_" + tag
    created = []
    root = Path(__file__).resolve().parents[1]
    passwords = {name: "T" + secrets.token_hex(20) for name in (owner, runtime)}
    result = {"desktop_success": False, "cleanup_success": False, "simulated": True}
    try:
        for name in (owner, runtime):
            admin(f'CREATE USER {name} IDENTIFIED BY "{passwords[name]}";')
            created.append(name)
            admin(f"GRANT CREATE SESSION TO {name};")
        admin(
            f"GRANT CREATE TABLE,CREATE VIEW,CREATE TRIGGER,CREATE SEQUENCE TO {owner};\nALTER USER {owner} QUOTA 50M ON USERS;\nGRANT EXECUTE ON SYS.DBMS_LOCK TO {owner};"
        )
        import oracledb

        from amrs.bootstrap import create_admin
        from amrs.migrations.runner import apply
        from tools.grant_runtime import grant_runtime

        with oracledb.connect(
            user=owner, password=passwords[owner], dsn="localhost:1521/FREEPDB1"
        ) as connection:
            apply(connection)
            create_admin(
                connection,
                "Synthetic test administrator",
                "desktop@example.test",
                "Synthetic-desktop-test-123",
                "Synthetic department",
            )
            grant_runtime(connection, runtime)
        env = dict(
            os.environ,
            AMRS_DB_USERNAME=runtime,
            AMRS_DB_SCHEMA=owner,
            AMRS_DB_PASSWORD=passwords[runtime],
            AMRS_ORACLE_DSN="localhost:1521/FREEPDB1",
            AMRS_CONFIG_FILE=str(root / "artifacts" / "no-private-config.json"),
            AMRS_DATA_DIR=str(root / "artifacts" / "desktop-data"),
            AMRS_LOG_DIR=str(root / "artifacts" / "desktop-logs"),
            QT_QPA_PLATFORM="windows",
            AMRS_REDUCE_MOTION="1",
        )
        process = subprocess.run(
            [sys.executable, "-m", "tools.desktop_smoke"],
            cwd=root,
            env=env,
            capture_output=True,
            timeout=50,
            check=False,
        )
        result["desktop_success"] = process.returncode == 0
    finally:
        for name in reversed(created):
            admin(f"DROP USER {name} CASCADE;")
        result["cleanup_success"] = True
        (root / "artifacts" / "desktop-native-summary.json").write_text(
            json.dumps(result, indent=2)
        )
        print(json.dumps(result))
    return 0 if result["desktop_success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
