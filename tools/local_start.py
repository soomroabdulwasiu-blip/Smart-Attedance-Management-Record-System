"""First-run local Oracle setup, then the normal AMRS desktop login."""

import getpass
import msvcrt
import os
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

DSN = "localhost:1521/FREEPDB1"


class SetupError(RuntimeError):
    """A safe, user-facing setup failure."""


def sqlplus_path() -> Path:
    configured = os.getenv("AMRS_LOCAL_SQLPLUS")
    on_path = shutil.which("sqlplus.exe")
    home = os.getenv("ORACLE_HOME")
    candidates = [
        Path(configured) if configured else None,
        Path(home) / "bin" / "sqlplus.exe" if home else None,
        Path(on_path) if on_path else None,
        *sorted(
            (Path("C:/app") / getpass.getuser() / "product").glob(
                "*/dbhomeFree/bin/sqlplus.exe"
            ),
            reverse=True,
        ),
    ]
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate.resolve()
    raise SetupError(
        "Local Oracle SQL*Plus was not found. Ask your Oracle administrator."
    )


def oracle_admin(executable: Path, statement: str) -> None:
    env = dict(os.environ, ORACLE_HOME=str(executable.parents[1]), ORACLE_SID="FREE")
    for key in ("LOCAL", "TWO_TASK", "SQLPATH"):
        env.pop(key, None)
    result = subprocess.run(
        [str(executable), "-L", "-S", "/", "as", "sysdba"],
        input=(
            "whenever oserror exit failure\nwhenever sqlerror exit failure\n"
            "set echo off verify off feedback off define off\n"
            "alter session set container=FREEPDB1;\n"
            f"{statement}\nexit success\n"
        ),
        cwd=executable.parent,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    codes = sorted(set(re.findall(r"(?:ORA|SP2)-\d+", result.stdout + result.stderr)))
    if result.returncode or codes:
        details = ", ".join(codes) or "OS authentication unavailable"
        raise SetupError(f"Local Oracle setup could not continue ({details}).")


def admin_details() -> tuple[str, str, str, str]:
    from amrs.mail_delivery import valid_email

    print("First run creates a separate local AMRS workspace with an empty roster.")
    print("Choose the administrator login for this workspace.")
    name = input("Admin name: ").strip()
    email = valid_email(input("Admin email: "))
    department = input("Department [General]: ").strip() or "General"
    password = getpass.getpass("Admin password (8+ characters): ")
    if (
        not name
        or not 8 <= len(password)
        or len(password.encode()) > 72
        or password != getpass.getpass("Confirm admin password: ")
    ):
        raise SetupError("Enter a name and matching passwords of 8 to 72 bytes.")
    return name, email, password, department


def provision(
    store, admin: tuple[str, str, str, str], executable: Path
) -> dict[str, str]:
    import oracledb

    from amrs.bootstrap import create_admin
    from amrs.configuration import verify_and_save
    from amrs.migrations.runner import apply
    from tools.grant_runtime import grant_runtime

    tag = secrets.token_hex(6).upper()
    owner = "AMRSL_O_" + tag
    runtime = "AMRSL_R_" + tag
    owner_password = "A" + secrets.token_hex(20)
    runtime_password = "A" + secrets.token_hex(20)
    created = []
    # An interrupted install must not silently create a second empty workspace.
    pending = store.path.with_name("setup-pending.txt")
    with pending.open("x", encoding="ascii") as marker:
        marker.write(f"{owner}\n{runtime}\n")
    try:
        for name, password in ((owner, owner_password), (runtime, runtime_password)):
            oracle_admin(executable, f'CREATE USER {name} IDENTIFIED BY "{password}";')
            created.append(name)
        oracle_admin(
            executable,
            f"GRANT CREATE SESSION TO {runtime};\n"
            f"GRANT CREATE SESSION, CREATE TABLE, CREATE VIEW, CREATE TRIGGER, "
            f"CREATE SEQUENCE TO {owner};\n"
            f"ALTER USER {owner} QUOTA 50M ON USERS;\n"
            f"GRANT EXECUTE ON SYS.DBMS_LOCK TO {owner};",
        )
        with oracledb.connect(
            user=owner,
            password=owner_password,
            dsn=DSN,
            tcp_connect_timeout=5,
            retry_count=0,
        ) as connection:
            connection.call_timeout = 10000
            apply(connection)
            create_admin(connection, *admin)
            grant_runtime(connection, runtime)
        oracle_admin(executable, f"ALTER USER {owner} ACCOUNT LOCK;")
        values = {
            "username": runtime,
            "schema": owner,
            "password": runtime_password,
            "dsn": DSN,
        }
        verify_and_save(values, remember=False)
        store.set("runtime", values)
    except (Exception, KeyboardInterrupt) as error:
        # Never clean up an account if CREATE did not positively confirm ownership.
        # A timeout/interrupt can leave uncertain Oracle state for DBA review.
        uncertain = isinstance(error, (subprocess.TimeoutExpired, KeyboardInterrupt))
        for name in reversed(created):
            try:
                oracle_admin(executable, f"DROP USER {name} CASCADE;")
            except SetupError, subprocess.TimeoutExpired, OSError:
                uncertain = True
        if uncertain:
            raise SetupError(
                "Local setup stopped partway through. Ask your DBA to review setup-pending.txt."
            ) from None
        pending.unlink()
        raise
    pending.unlink(missing_ok=True)
    print("Local Oracle workspace ready. Sign in as Admin with the account you chose.")
    return values


def prepare(profile: Path) -> None:
    # Keep this launch separate from any saved legacy configuration or environment.
    for name in (
        "AMRS_DB_USERNAME",
        "AMRS_DB_SCHEMA",
        "AMRS_DB_PASSWORD",
        "AMRS_ORACLE_DSN",
        "AMRS_CONFIG_FILE",
        "AMRS_DATA_DIR",
        "AMRS_LOG_DIR",
    ):
        os.environ.pop(name, None)
    os.environ["AMRS_PROFILE_DIR"] = str(profile)

    from amrs.configuration import install, verify_and_save
    from amrs.secure_store import SecretStore

    profile.mkdir(parents=True, exist_ok=True)
    store = SecretStore("database", directory=profile)
    with (profile / "startup.lock").open("a+b") as lock:
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise SetupError(
                "AMRS is already preparing this workspace. Try again shortly."
            ) from None
        saved = store.get("runtime")
        if saved:
            verify_and_save(saved, remember=False)
            return
        if store.path.exists() or (profile / "setup-pending.txt").exists():
            raise SetupError(
                "The local workspace needs DBA review before setup can continue."
            )
        executable = sqlplus_path()
        oracle_admin(executable, "select 1 from dual;")
        install(provision(store, admin_details(), executable))


def main() -> int:
    import oracledb

    from amrs.migrations.runner import MigrationError

    profile = Path(os.environ["LOCALAPPDATA"]) / "AMRS_Local"
    try:
        prepare(profile)
    except (SetupError, MigrationError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except oracledb.Error as exc:
        code = getattr(exc.args[0], "full_code", "Oracle error")
        print(
            f"Oracle is unavailable or the workspace could not connect ({code}).",
            file=sys.stderr,
        )
        return 1
    except KeyboardInterrupt, EOFError, OSError, subprocess.TimeoutExpired:
        print(
            "Local setup did not finish. Check the Oracle service and try again.",
            file=sys.stderr,
        )
        return 1

    from amrs.gui import main as launch

    return launch()


if __name__ == "__main__":
    raise SystemExit(main())
