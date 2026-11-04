"""Explicit, metadata-only legacy baseline adoption; never an automatic upgrade.

The DBA supplies a separate reference schema built from an exact source prefix.
Only the migration registry is added to a compatible legacy schema. Application
rows are neither read nor rewritten by this module. A reviewed backup/restore
approval is required before that registry write.
"""

import hashlib
import json
import re
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import oracledb

from .runner import REGISTRY, MigrationError, read_migrations, registry_exists


def _rows(connection, query):
    cur = connection.cursor()
    cur.execute(query)
    names = [column[0].lower() for column in cur.description]
    return [dict(zip(names, values)) for values in cur]


def canonical_sql(value, schema=""):
    """Normalize formatting outside literals; never fold string-literal case."""
    if value is None:
        return None
    parts = re.split(r"('(?:''|[^'])*')", str(value))
    for index in range(0, len(parts), 2):
        text = re.sub(r"\s+", " ", parts[index]).strip()
        if schema:
            text = text.replace('"' + schema + '".', '"<OWNER>".')
            text = re.sub(r"\b" + re.escape(schema) + r"\.", "<OWNER>.", text)
        quoted = re.split(r'("(?:""|[^"])*")', text)
        parts[index] = "".join(
            part if at % 2 else part.upper() for at, part in enumerate(quoted)
        )
    return " ".join(part for part in parts if part).strip().rstrip(";")


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def identity(connection):
    row = _rows(
        connection,
        """SELECT SYS_CONTEXT('USERENV','DB_UNIQUE_NAME') db_name,
        SYS_CONTEXT('USERENV','CON_NAME') container_name,
        SYS_CONTEXT('USERENV','SESSION_USER') session_user,
        SYS_CONTEXT('USERENV','CURRENT_SCHEMA') schema_name FROM dual""",
    )[0]
    if row["session_user"] != row["schema_name"]:
        raise MigrationError(
            "Adoption requires a direct connection as the schema owner."
        )
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,29}", row["schema_name"] or ""):
        raise MigrationError("Quoted or unsupported schema identifiers are refused.")
    return row


def snapshot(connection):
    """Read only this owner's dictionary metadata, excluding the registry."""
    owner = identity(connection)["schema_name"]
    tables = _rows(
        connection,
        "SELECT table_name,temporary,partitioned,iot_type,nested FROM user_tables WHERE table_name<>'SCHEMA_MIGRATIONS' ORDER BY table_name",
    )
    table_names = {row["table_name"] for row in tables}
    columns = _rows(
        connection,
        """SELECT table_name,column_name,column_id,data_type,data_length,
        data_precision,data_scale,char_used,char_length,nullable,data_default,
        identity_column,virtual_column FROM user_tab_cols
        WHERE hidden_column='NO' ORDER BY table_name,column_id""",
    )
    columns = [row for row in columns if row["table_name"] in table_names]
    invisible_columns = [
        row
        for row in _rows(
            connection,
            "SELECT table_name,column_name FROM user_tab_cols WHERE hidden_column='YES' AND user_generated='YES' ORDER BY table_name,column_name",
        )
        if row["table_name"] in table_names
    ]
    for row in columns:
        row["data_default"] = (
            "<IDENTITY_SEQUENCE>"
            if row["identity_column"] == "YES"
            else canonical_sql(row["data_default"], owner)
        )
    identities = _rows(
        connection,
        "SELECT table_name,column_name,generation_type,identity_options,sequence_name FROM user_tab_identity_cols ORDER BY table_name,column_name",
    )
    identity_sequences = {row.pop("sequence_name") for row in identities}
    for row in identities:
        # START WITH belongs to the original DDL, not the current sequence counter.
        row["identity_options"] = canonical_sql(row["identity_options"], owner)
    constraints = _rows(
        connection,
        """SELECT constraint_name,table_name,constraint_type,search_condition,
        r_owner,r_constraint_name,delete_rule,status,deferrable,deferred,validated,
        rely,generated,index_name FROM user_constraints ORDER BY table_name,constraint_name""",
    )
    constraint_columns = _rows(
        connection,
        "SELECT constraint_name,column_name,position FROM user_cons_columns ORDER BY constraint_name,position",
    )
    columns_by_constraint: dict[str, list[str]] = {}
    for row in constraint_columns:
        columns_by_constraint.setdefault(row["constraint_name"], []).append(
            row["column_name"]
        )
    by_name = {row["constraint_name"]: row for row in constraints}
    indexed_constraints = {}
    result_constraints = []
    for row in constraints:
        if row["table_name"] not in table_names:
            continue
        row = dict(row)
        name = row.pop("constraint_name")
        row["columns"] = columns_by_constraint.get(name, [])
        generated = row.pop("generated") == "GENERATED NAME"
        row["name"] = "<GENERATED>" if generated else name
        referenced = row.pop("r_constraint_name")
        if referenced:
            other = by_name.get(referenced)
            if row["r_owner"] != owner or other is None:
                raise MigrationError("External-schema foreign keys cannot be adopted.")
            row["referenced_table"] = other["table_name"]
            row["referenced_columns"] = columns_by_constraint.get(referenced, [])
        row["r_owner"] = "<OWNER>" if row["r_owner"] == owner else row["r_owner"]
        index = row.pop("index_name")
        if index:
            indexed_constraints[index] = (
                row["table_name"]
                + ":"
                + row["constraint_type"]
                + ":"
                + ",".join(row["columns"])
            )
        row["search_condition"] = canonical_sql(row["search_condition"], owner)
        result_constraints.append(row)
    indexes = _rows(
        connection,
        "SELECT index_name,table_name,index_type,uniqueness,status,visibility FROM user_indexes ORDER BY table_name,index_name",
    )
    index_columns = _rows(
        connection,
        "SELECT index_name,column_name,column_position,descend FROM user_ind_columns ORDER BY index_name,column_position",
    )
    expressions = _rows(
        connection,
        "SELECT index_name,column_position,column_expression FROM user_ind_expressions ORDER BY index_name,column_position",
    )
    expression_map = {
        (row["index_name"], row["column_position"]): canonical_sql(
            row["column_expression"], owner
        )
        for row in expressions
    }
    index_parts: dict[str, list[dict[str, object]]] = {}
    for row in index_columns:
        index_parts.setdefault(row["index_name"], []).append(
            {
                "column": expression_map.get(
                    (row["index_name"], row["column_position"]), row["column_name"]
                ),
                "direction": row["descend"],
            }
        )
    result_indexes = []
    for row in indexes:
        if row["table_name"] not in table_names:
            continue
        row = dict(row)
        name = row.pop("index_name")
        row["name"] = (
            "<CONSTRAINT>:" + indexed_constraints[name]
            if name in indexed_constraints
            else name
        )
        row["parts"] = index_parts.get(name, [])
        result_indexes.append(row)
    triggers = _rows(
        connection,
        "SELECT trigger_name,table_name,trigger_type,triggering_event,status,when_clause,trigger_body FROM user_triggers ORDER BY trigger_name",
    )
    for row in triggers:
        row["trigger_body"] = canonical_sql(row["trigger_body"], owner)
        row["when_clause"] = canonical_sql(row["when_clause"], owner)
    views = _rows(
        connection, "SELECT view_name,text FROM user_views ORDER BY view_name"
    )
    for row in views:
        row["text"] = canonical_sql(row["text"], owner)
    sequences = _rows(
        connection,
        "SELECT sequence_name,min_value,max_value,increment_by,cycle_flag,order_flag,cache_size FROM user_sequences ORDER BY sequence_name",
    )
    sequences = [
        row for row in sequences if row["sequence_name"] not in identity_sequences
    ]
    objects = _rows(
        connection,
        "SELECT object_name,object_type,status FROM user_objects ORDER BY object_type,object_name",
    )
    unexpected = [
        row
        for row in objects
        if row["object_type"] not in {"TABLE", "INDEX", "TRIGGER", "VIEW", "SEQUENCE"}
    ]
    invalid = [row for row in objects if row["status"] != "VALID"]
    result = {
        "tables": tables,
        "columns": columns,
        "invisible_columns": invisible_columns,
        "identities": identities,
        "constraints": result_constraints,
        "indexes": result_indexes,
        "triggers": triggers,
        "views": views,
        "sequences": sequences,
        "unexpected_objects": unexpected,
        "invalid_objects": invalid,
    }
    # Generated constraint/index names differ between identical fresh schemas.
    return {
        key: sorted(values, key=lambda row: json.dumps(row, sort_keys=True))
        for key, values in result.items()
    }


def _prefix(through):
    migrations = read_migrations()
    versions = [migration.version for migration in migrations]
    if through not in versions:
        raise MigrationError("Unknown adoption baseline version.")
    return migrations[: versions.index(through) + 1]


def plan(target, reference, through):
    """Return a redacted comparison; no DDL or application-data queries."""
    target_identity = identity(target)
    reference_identity = identity(reference)
    if target_identity == reference_identity:
        raise MigrationError("A separate trusted reference schema is required.")
    if registry_exists(target.cursor()):
        raise MigrationError(
            "Target already has migration history; use normal migration review."
        )
    prefix = _prefix(through)
    history = _rows(
        reference,
        "SELECT version,checksum,state,last_step FROM schema_migrations ORDER BY version",
    )
    expected_history = [
        {
            "version": m.version,
            "checksum": m.checksum,
            "state": "APPLIED",
            "last_step": len(m.statements),
        }
        for m in prefix
    ]
    if history != expected_history:
        raise MigrationError(
            "Reference schema must be migrated to exactly the selected source prefix."
        )
    observed = snapshot(target)
    expected = snapshot(reference)
    differences = [key for key in expected if observed[key] != expected[key]]
    if observed["unexpected_objects"] or observed["invalid_objects"]:
        differences.extend(
            key
            for key in ("unexpected_objects", "invalid_objects")
            if observed[key] and key not in differences
        )
    return {
        "format": 1,
        "target": target_identity,
        "through": through,
        "source_checksums": {m.version: m.checksum for m in prefix},
        "target_metadata_sha256": fingerprint(observed),
        "reference_metadata_sha256": fingerprint(expected),
        "differences": differences,
        "compatible": not differences,
    }


def _file_digest(path):
    if not path.is_absolute() or not path.is_file() or path.stat().st_size == 0:
        raise MigrationError(
            "Backup and restore-verification artifacts must be nonempty absolute files."
        )
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while data := handle.read(1024 * 1024):
            digest.update(data)
    return digest.hexdigest()


def validate_approval(approval, adoption_plan):
    """Verify reviewed artifact bindings; restore correctness remains DBA attestation."""
    if approval.get("plan_sha256") != fingerprint(adoption_plan):
        raise MigrationError("Approval does not match the reviewed adoption plan.")
    if (
        approval.get("approved") is not True
        or approval.get("restore_verified") is not True
        or approval.get("role_seeds_verified") is not True
    ):
        raise MigrationError(
            "Explicit approval, verified restore and role-seed verification are required."
        )
    if not str(approval.get("approved_by", "")).strip():
        raise MigrationError("A responsible approver must be recorded.")
    try:
        approved_at = datetime.fromisoformat(approval["approved_at"])
        if approved_at.tzinfo is None or not timedelta(0) <= datetime.now(
            UTC
        ) - approved_at <= timedelta(days=1):
            raise ValueError
        for key in ("backup", "restore_report"):
            if _file_digest(Path(approval[key + "_file"])) != approval[key + "_sha256"]:
                raise MigrationError(
                    "Backup or restore-verification artifact checksum mismatch."
                )
    except KeyError, TypeError, ValueError, OSError:
        raise MigrationError(
            "Approval must name verified artifacts and a timezone-aware approval less than 24 hours old."
        ) from None


@contextmanager
def _lock(connection):
    schema = identity(connection)["schema_name"]
    lock_id = int(
        hashlib.sha256(("amrs-migrate-" + schema).encode()).hexdigest()[:7], 16
    )
    cur = connection.cursor()
    try:
        status = cur.callfunc("DBMS_LOCK.REQUEST", int, [lock_id, 6, 0, False])
    except oracledb.Error:
        raise MigrationError(
            "Migration owner needs EXECUTE on SYS.DBMS_LOCK."
        ) from None
    if status not in (0, 4):
        raise MigrationError("Another migration or adoption is running.")
    try:
        yield
    finally:
        cur.callfunc("DBMS_LOCK.RELEASE", int, [lock_id])


def adopt(target, reference, reviewed_plan, approval):
    """Add only a baseline registry after a fresh exact comparison and approval."""
    with _lock(target):
        current = plan(target, reference, reviewed_plan.get("through"))
        if current != reviewed_plan or current.get("compatible") is not True:
            raise MigrationError(
                "Schema changed or differs from the reviewed reference; no baseline was written."
            )
        validate_approval(approval, current)
        if plan(target, reference, current["through"]) != current:
            raise MigrationError(
                "Schema changed during backup evidence validation; no baseline was written."
            )
        prefix = _prefix(current["through"])
        cur = target.cursor()
        cur.execute(REGISTRY)
        try:
            cur.executemany(
                "INSERT INTO schema_migrations(version,checksum,state,last_step) VALUES(:v,:c,'APPLIED',:s)",
                [
                    {"v": m.version, "c": m.checksum, "s": len(m.statements)}
                    for m in prefix
                ],
            )
            target.commit()
        except oracledb.Error:
            target.rollback()
            raise MigrationError(
                "Baseline write interrupted. Registry DDL may remain; an administrator must inspect it before recovery."
            ) from None
        return [m.version for m in prefix]
