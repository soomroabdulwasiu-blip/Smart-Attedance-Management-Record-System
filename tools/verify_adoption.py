"""Synthetic native-Oracle adoption checks; refuses non-disposable account names."""

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path

from amrs.migrations.adoption import adopt, fingerprint, identity, plan
from amrs.migrations.runner import MigrationError, registry_exists


def verify_fixture(target, reference, temporarydir):
    """Both owners must already contain migrations 001 and 002, with registries.

    The synthetic target registry is removed to model an unversioned legacy
    schema. Only generated AMRST_* owners are eligible. Backup fixture bytes
    exercise approval binding; they are not claimed as a real restored backup.
    """
    for connection in (target, reference):
        owner = identity(connection)["schema_name"]
        if not re.fullmatch(r"AMRST_[A-Z]_[A-F0-9]{10}", owner):
            raise RuntimeError("Adoption fixture requires disposable AMRST owners.")
    assert identity(target) != identity(reference)
    cur = target.cursor()
    cur.execute(
        "INSERT INTO departments(dept_name) VALUES ('Adoption row-preservation fixture')"
    )
    target.commit()
    before = {}
    for table in ("departments", "users", "students", "attendance"):
        cur.execute("SELECT COUNT(*) FROM " + table)
        before[table] = cur.fetchone()[0]
    cur.execute("DROP TABLE schema_migrations PURGE")
    reviewed = plan(target, reference, "002")
    assert reviewed["compatible"], "Legacy metadata comparison differs: " + str(
        reviewed["differences"]
    )
    directory = Path(temporarydir)
    directory.mkdir(parents=True, exist_ok=True)
    approval = {
        "plan_sha256": fingerprint(reviewed),
        "approved": True,
        "restore_verified": True,
        "role_seeds_verified": True,
        "approved_by": "Synthetic test operator",
        "approved_at": datetime.now(UTC).isoformat(),
    }
    for key in ("backup", "restore_report"):
        path = (directory / (key + ".fixture")).resolve()
        content = ("Synthetic approval binding fixture: " + key).encode()
        path.write_bytes(content)
        approval[key + "_file"] = str(path)
        approval[key + "_sha256"] = hashlib.sha256(content).hexdigest()
    for invalid in (
        {**approval, "approved": False},
        {**approval, "backup_sha256": "0" * 64},
    ):
        try:
            adopt(target, reference, reviewed, invalid)
        except MigrationError:
            pass
        else:
            raise AssertionError(
                "Unapproved or mismatched backup adoption was accepted"
            )
        assert not registry_exists(target.cursor())
    cur.execute("CREATE TABLE amrs_test_adoption_extra(id NUMBER)")
    divergent = plan(target, reference, "002")
    assert not divergent["compatible"]
    try:
        adopt(target, reference, reviewed, approval)
    except MigrationError:
        pass
    else:
        raise AssertionError("Divergent metadata was adopted")
    assert not registry_exists(target.cursor())
    cur.execute("DROP TABLE amrs_test_adoption_extra PURGE")
    assert adopt(target, reference, reviewed, approval) == ["001", "002"]
    for table, count in before.items():
        cur.execute("SELECT COUNT(*) FROM " + table)
        assert cur.fetchone()[0] == count
    try:
        adopt(target, reference, reviewed, approval)
    except MigrationError:
        pass
    else:
        raise AssertionError("Already-versioned target was adopted again")
    return {
        "metadata_match": True,
        "approval_guards": True,
        "drift_refused": True,
        "rows_preserved": True,
    }
