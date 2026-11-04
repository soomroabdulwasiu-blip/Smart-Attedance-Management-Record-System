"""Disposable schema verification using native SQLPlus OS authentication.

Never load private credentials. Names/passwords are generated in memory, and
only schemas created by this invocation are eligible for cleanup.
"""

import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

from tools.legacy_test_check import PRIVATE_FIXTURES, SAFE

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "artifacts"


def admin(sql):
    executable = os.environ.get("AMRS_TEST_SQLPLUS", "sqlplus")
    script = (
        "whenever sqlerror exit failure\nset echo off verify off feedback off heading off\nalter session set container=FREEPDB1;\n"
        + sql
        + "\nexit\n"
    )
    env = dict(os.environ, ORACLE_SID="FREE")
    result = subprocess.run(
        [executable, "-L", "-S", "/", "as", "sysdba"],
        input=script,
        text=True,
        capture_output=True,
        env=env,
        timeout=45,
        check=False,
    )
    if result.returncode:
        codes = ",".join(
            sorted(set(re.findall(r"ORA-\d+", result.stdout + result.stderr)))
        )
        raise RuntimeError(
            "Native test administration failed: "
            + (codes or "OS authentication unavailable")
        )


def main():
    if os.environ.get("AMRS_ALLOW_NATIVE_ISOLATED_TEST") != "1":
        raise RuntimeError("Explicit AMRS_ALLOW_NATIVE_ISOLATED_TEST=1 is required.")
    REPORTS.mkdir(exist_ok=True)
    tag = uuid.uuid4().hex[:10].upper()
    owner = "AMRST_M_" + tag
    runtime = "AMRST_R_" + tag
    reference = "AMRST_F_" + tag
    owner_pw = "T" + secrets.token_hex(20)
    runtime_pw = "T" + secrets.token_hex(20)
    reference_pw = "T" + secrets.token_hex(20)
    created = []
    legacy: list[dict[str, str]] = []
    summary: dict[str, object] = {
        "started_utc": datetime.now(UTC).isoformat(),
        "environment": "Native Oracle FREEPDB1; disposable owner/runtime users",
        "oracle_connectivity": False,
        "pytest_success": False,
        "migration_checks_success": False,
        "cleanup_success": False,
        "docker": "Not run: owner selected native testing and prohibited WSL/Windows component changes",
    }
    try:
        for name, password in (
            (owner, owner_pw),
            (runtime, runtime_pw),
            (reference, reference_pw),
        ):
            admin(f'CREATE USER {name} IDENTIFIED BY "{password}";')
            created.append(name)
            admin(f"GRANT CREATE SESSION TO {name};")
        for name in (owner, reference):
            admin(
                f"GRANT CREATE TABLE, CREATE VIEW, CREATE TRIGGER, CREATE SEQUENCE TO {name};\nALTER USER {name} QUOTA 50M ON USERS;\nGRANT EXECUTE ON SYS.DBMS_LOCK TO {name};"
            )
        os.environ.update(
            AMRS_DB_USERNAME=runtime,
            AMRS_DB_PASSWORD=runtime_pw,
            AMRS_DB_SCHEMA=owner,
            AMRS_ORACLE_DSN="localhost:1521/FREEPDB1",
            AMRS_CONFIG_FILE=str(REPORTS / "no-private-config.json"),
            AMRS_DATA_DIR=str(REPORTS / ("runtime-" + tag)),
            AMRS_LOG_DIR=str(REPORTS / ("logs-" + tag)),
        )
        import oracledb

        from amrs.bootstrap import create_admin
        from amrs.migrations.runner import (
            Migration,
            MigrationError,
            apply,
            read_migrations,
        )
        from tools.grant_runtime import grant_runtime

        with oracledb.connect(
            user=owner, password=owner_pw, dsn=os.environ["AMRS_ORACLE_DSN"]
        ) as connection:
            migrations = read_migrations()
            assert apply(connection, migrations[:2]) == ["001", "002"]
            cur = connection.cursor()
            cur.execute(
                "INSERT INTO departments(dept_name) VALUES ('Migration preservation fixture')"
            )
            connection.commit()
            from tools.verify_adoption import verify_fixture

            with oracledb.connect(
                user=reference, password=reference_pw, dsn=os.environ["AMRS_ORACLE_DSN"]
            ) as ref:
                apply(ref, migrations[:2])
                with tempfile.TemporaryDirectory(prefix="amrs-adoption-") as temporary:
                    summary["legacy_adoption"] = verify_fixture(
                        connection, ref, temporary
                    )
            assert apply(connection) == [m.version for m in migrations[2:]]
            cur.execute(
                "SELECT COUNT(*) FROM departments WHERE dept_name='Migration preservation fixture'"
            )
            assert cur.fetchone()[0] == 1
            assert apply(connection) == []
            migrations = read_migrations()
            changed = [
                Migration("001", "0" * 64, migrations[0].statements),
                *migrations[1:],
            ]
            try:
                apply(connection, changed)
            except MigrationError:
                pass
            else:
                raise AssertionError("Changed checksum was accepted")
            create_admin(
                connection,
                "Test Admin",
                "admin@example.test",
                "Test-admin-password-123",
                "Test department",
            )
            try:
                create_admin(
                    connection,
                    "Second Admin",
                    "second@example.test",
                    "Test-admin-password-123",
                    "Other",
                )
            except ValueError:
                connection.rollback()
            else:
                raise AssertionError("Repeated bootstrap accepted")
            grant_runtime(connection, runtime)
        from amrs import db
        from amrs.recovery import ensure_schema

        ensure_schema()
        with db.connection() as connection:
            cur = connection.cursor()
            cur.execute("SELECT 1,SYS_CONTEXT('USERENV','CURRENT_SCHEMA') FROM dual")
            assert cur.fetchone() == (1, owner)
            summary["oracle_connectivity"] = True
            print(
                "Native Oracle runtime connectivity and schema selection: verified.",
                flush=True,
            )
            try:
                connection.cursor().execute("CREATE TABLE must_not_create(id NUMBER)")
            except oracledb.DatabaseError as exc:
                assert exc.args[0].code == 1031
            else:
                raise AssertionError("Runtime account has DDL privileges")
        env = dict(os.environ, AMRS_TEST_ORACLE="1", QT_QPA_PLATFORM="offscreen")
        startup = subprocess.run(
            [sys.executable, "main.py", "--smoke-test"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            timeout=30,
            check=False,
        )
        summary["desktop_startup_success"] = startup.returncode == 0
        summary["desktop_startup_exit_code"] = startup.returncode
        if startup.returncode:
            raise RuntimeError(
                "Desktop startup failed with exit code "
                + str(startup.returncode)
                + "; private child logs were not printed."
            )
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests",
                "-q",
                "-m",
                "not legacy",
                "--cov=amrs",
                "--cov-report=json:" + str(REPORTS / "coverage-native.json"),
                "--cov-report=xml:" + str(REPORTS / "coverage.xml"),
                "--cov-fail-under=60",
                "--junitxml",
                str(REPORTS / "native-pytest.xml"),
                "-p",
                "no:cacheprovider",
                "--basetemp",
                str(ROOT.parent / ("pytest-native-" + tag)),
            ],
            cwd=ROOT,
            env=env,
            timeout=240,
            check=False,
        )
        summary["pytest_success"] = result.returncode == 0
        legacy_run = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_legacy_scenarios.py",
                "-q",
                "--junitxml",
                str(REPORTS / "native-legacy.xml"),
                "-p",
                "no:cacheprovider",
                "--basetemp",
                str(ROOT.parent / ("pytest-legacy-" + tag)),
            ],
            cwd=ROOT,
            env=env,
            timeout=240,
            check=False,
        )
        cases = ET.parse(REPORTS / "native-legacy.xml").getroot().iter("testcase")
        legacy = []
        for case in cases:
            name = case.attrib["name"].split("[", 1)[1].rstrip("]")
            status = (
                "not_run"
                if case.find("skipped") is not None
                else (
                    "failed"
                    if case.find("failure") is not None
                    or case.find("error") is not None
                    else "passed"
                )
            )
            legacy.append(
                {
                    "test": name,
                    "status": status,
                    "detail": "Private biometric fixtures unavailable; not a Docker dependency."
                    if status == "not_run"
                    else (
                        "Scenario failed; inspect the sanitized child diagnostic."
                        if status == "failed"
                        else ""
                    ),
                }
            )
        if legacy_run.returncode and not any(r["status"] == "failed" for r in legacy):
            raise RuntimeError("Legacy test process failed outside its scenarios.")
        expected_cases = (*SAFE, *PRIVATE_FIXTURES)
        if sorted(row["test"] for row in legacy) != sorted(expected_cases):
            raise RuntimeError("Legacy scenario collection was incomplete.")
        (REPORTS / "legacy-results.json").write_text(
            json.dumps(legacy, indent=2), encoding="utf-8"
        )
        summary["legacy"] = legacy
        print(
            "Legacy scenarios: "
            + str(sum(r["status"] == "passed" for r in legacy))
            + " passed, "
            + str(sum(r["status"] == "failed" for r in legacy))
            + " failed, "
            + str(sum(r["status"] == "not_run" for r in legacy))
            + " not run."
        )
        # Exercise a recoverable failed forward migration only in this disposable schema.
        with oracledb.connect(
            user=owner, password=owner_pw, dsn=os.environ["AMRS_ORACLE_DSN"]
        ) as connection:
            steps = (
                "CREATE TABLE amrs_test_checkpoint(id NUMBER)",
                "INSERT INTO amrs_test_dependency(id) VALUES (1)",
            )
            next_version = f"{int(read_migrations()[-1].version) + 1:03d}"
            forward = Migration(next_version, "f" * 64, steps)
            try:
                apply(connection, [*read_migrations(), forward])
            except MigrationError:
                pass
            else:
                raise AssertionError(
                    "Missing test dependency should interrupt migration"
                )
            cur = connection.cursor()
            cur.execute(
                "SELECT last_step,state FROM schema_migrations WHERE version=:version",
                {"version": next_version},
            )
            assert cur.fetchone() == (1, "APPLYING")
            cur.execute("CREATE TABLE amrs_test_dependency(id NUMBER)")
            assert apply(connection, [*read_migrations(), forward]) == [next_version]
            cur.execute("SELECT COUNT(*) FROM amrs_test_dependency")
            assert cur.fetchone()[0] == 1
        print(
            "PASS: fresh schema, row preservation, idempotency, checksum guard, first admin, runtime DDL denial and interrupted migration retry."
        )
        summary["migration_checks_success"] = True
    finally:
        try:
            from amrs import db

            if db._pool is not None:
                db._pool.close(force=True)
        finally:
            for name in reversed(created):
                if not re.fullmatch(r"AMRST_[MRF]_" + tag, name):
                    raise RuntimeError("Cleanup target refused")
                admin(f"DROP USER {name} CASCADE;")
            summary["cleanup_success"] = True
            summary["finished_utc"] = datetime.now(UTC).isoformat()
            (REPORTS / "native-summary.json").write_text(
                json.dumps(summary, indent=2), encoding="utf-8"
            )
            print(
                "Disposable test schemas removed. Production records were not queried or modified."
            )
    if not summary["pytest_success"] or any(r["status"] == "failed" for r in legacy):
        raise RuntimeError(
            "One or more test scenarios failed; see the sanitized artifacts."
        )


if __name__ == "__main__":
    main()
