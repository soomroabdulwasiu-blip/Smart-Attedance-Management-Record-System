"""Forward-only Oracle migrations with checksum validation and checkpointed DDL."""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import oracledb

SCHEMA = Path(__file__).resolve().parents[2] / "db" / "schema"
REGISTRY = """CREATE TABLE schema_migrations (
 version VARCHAR2(10) PRIMARY KEY, applied_at TIMESTAMP DEFAULT SYS_EXTRACT_UTC(SYSTIMESTAMP) NOT NULL,
 checksum VARCHAR2(64) NOT NULL, state VARCHAR2(12) NOT NULL,
 last_step NUMBER DEFAULT 0 NOT NULL)"""


class MigrationError(RuntimeError):
    """An unsafe, incomplete or incompatible schema transition was refused."""


@dataclass(frozen=True)
class Migration:
    version: str
    checksum: str
    statements: tuple[str, ...]


def read_migrations(directory: Path = SCHEMA) -> list[Migration]:
    result = []
    for path in sorted(directory.glob("[0-9][0-9][0-9]_*.sql")):
        source = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        statements = tuple(
            s.strip()
            for s in re.split(r"^/\s*$", source, flags=re.MULTILINE)
            if s.strip()
        )
        result.append(
            Migration(
                path.name[:3], hashlib.sha256(source.encode()).hexdigest(), statements
            )
        )
    if not result or len({m.version for m in result}) != len(result):
        raise MigrationError("Missing migrations or duplicate version numbers.")
    return result


def registry_exists(cur) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM all_tables WHERE owner=sys_context('USERENV','CURRENT_SCHEMA') AND table_name='SCHEMA_MIGRATIONS'"
    )
    return bool(cur.fetchone()[0])


def validate_history(existing, migrations):
    """A registry must be an ordered prefix with at most its final step pending."""
    versions = [migration.version for migration in migrations]
    if sorted(existing) != versions[: len(existing)]:
        raise MigrationError(
            "Migration history is not an ordered source prefix; refusing changes."
        )
    known = {migration.version: migration for migration in migrations}
    for index, version in enumerate(sorted(existing)):
        checksum, state, step = existing[version]
        migration = known[version]
        if checksum != migration.checksum:
            raise MigrationError(
                "Migration history checksum mismatch; refusing changes."
            )
        if not isinstance(step, int) or not 0 <= step <= len(migration.statements):
            raise MigrationError(
                "Migration checkpoint is invalid; administrator review required."
            )
        if state == "APPLIED":
            if step != len(migration.statements):
                raise MigrationError("Applied migration has an incomplete checkpoint.")
        elif state != "APPLYING" or index != len(existing) - 1:
            raise MigrationError(
                "Migration state is invalid or precedes a later migration."
            )


def apply(connection, migrations=None) -> list[str]:
    migrations = read_migrations() if migrations is None else migrations
    cur = connection.cursor()
    # Use a schema-specific advisory lock that survives Oracle's implicit DDL commits.
    cur.execute(
        "SELECT sys_context('USERENV','CURRENT_SCHEMA'),sys_context('USERENV','SESSION_USER') FROM dual"
    )
    schema, session_user = cur.fetchone()
    if schema != session_user:
        raise MigrationError(
            "Migrations require a direct connection as the schema owner."
        )
    lock_id = int(
        hashlib.sha256(("amrs-migrate-" + schema).encode()).hexdigest()[:7], 16
    )
    try:
        result = cur.callfunc("DBMS_LOCK.REQUEST", int, [lock_id, 6, 0, False])
    except oracledb.Error:
        raise MigrationError(
            "Migration owner needs an explicit EXECUTE grant on SYS.DBMS_LOCK."
        ) from None
    if result not in (0, 4):
        raise MigrationError("Another migration is running; no changes made.")
    applied = []
    try:
        if not registry_exists(cur):
            cur.execute(
                "SELECT COUNT(*) FROM user_tables WHERE table_name IN ('USERS','STUDENTS','ATTENDANCE')"
            )
            if cur.fetchone()[0]:
                raise MigrationError(
                    "Legacy schema detected. Back up and review schema adoption before migrating it."
                )
            cur.execute(REGISTRY)
        cur.execute(
            "SELECT version,checksum,state,last_step FROM schema_migrations ORDER BY version"
        )
        existing = {row[0]: row[1:] for row in cur}
        validate_history(existing, migrations)
        for migration in migrations:
            old = existing.get(migration.version)
            if old and old[1] == "APPLIED":
                continue
            if not old:
                cur.execute(
                    "INSERT INTO schema_migrations(version,checksum,state) VALUES(:v,:c,'APPLYING')",
                    {"v": migration.version, "c": migration.checksum},
                )
                connection.commit()
            start = int(old[2]) if old else 0
            for index, statement in enumerate(
                migration.statements[start:], start=start + 1
            ):
                try:
                    cur.execute(statement)
                    # Oracle DDL commits implicitly. Checkpoint each successful statement.
                    cur.execute(
                        "UPDATE schema_migrations SET last_step=:s WHERE version=:v",
                        {"s": index, "v": migration.version},
                    )
                    connection.commit()
                except oracledb.Error as exc:
                    connection.rollback()
                    code = getattr(exc.args[0], "code", None) if exc.args else None
                    raise MigrationError(
                        f"Migration {migration.version}, step {index} failed (Oracle code {code}); inspect in the isolated test environment."
                    ) from None
            cur.execute(
                "UPDATE schema_migrations SET state='APPLIED',applied_at=SYS_EXTRACT_UTC(SYSTIMESTAMP) WHERE version=:v",
                {"v": migration.version},
            )
            connection.commit()
            applied.append(migration.version)
        return applied
    finally:
        cur.callfunc("DBMS_LOCK.RELEASE", int, [lock_id])


def require_current(connection) -> None:
    cur = connection.cursor()
    if not registry_exists(cur):
        raise MigrationError(
            "Database setup is required. Ask the administrator to run python -m amrs.migrate up."
        )
    cur.execute("SELECT version,checksum,state,last_step FROM schema_migrations")
    existing = {r[0]: (r[1], r[2], r[3]) for r in cur}
    migrations = read_migrations()
    validate_history(existing, migrations)
    if existing != {
        m.version: (m.checksum, "APPLIED", len(m.statements)) for m in migrations
    }:
        raise MigrationError(
            "Database schema version needs administrator review; no automatic DDL was run."
        )
