import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from amrs.migrations.adoption import canonical_sql, fingerprint, validate_approval
from amrs.migrations.runner import Migration, MigrationError, validate_history


def test_metadata_normalization_preserves_literal_and_quoted_identifier_case():
    assert canonical_sql(" CURRENT_TIMESTAMP \n") == "CURRENT_TIMESTAMP"
    assert canonical_sql("'present'") != canonical_sql("'PRESENT'")
    assert canonical_sql('"Mixed"') != canonical_sql('"MIXED"')
    assert canonical_sql('"FIRST"."TABLE"', "FIRST") == canonical_sql(
        '"SECOND"."TABLE"', "SECOND"
    )
    assert canonical_sql("'FIRST.TABLE'", "FIRST") == "'FIRST.TABLE'"


def _approval(tmp_path, reviewed):
    approval = {
        "plan_sha256": fingerprint(reviewed),
        "approved": True,
        "restore_verified": True,
        "role_seeds_verified": True,
        "approved_by": "Test DBA",
        "approved_at": datetime.now(UTC).isoformat(),
    }
    for key in ("backup", "restore_report"):
        content = (key + " synthetic artifact").encode()
        path = tmp_path / key
        path.write_bytes(content)
        approval[key + "_file"] = str(path.resolve())
        approval[key + "_sha256"] = hashlib.sha256(content).hexdigest()
    return approval


def test_approval_binds_plan_and_nonempty_artifacts(tmp_path):
    reviewed = {"target": "synthetic", "fingerprint": "a" * 64}
    approval = _approval(tmp_path, reviewed)
    validate_approval(approval, reviewed)
    with pytest.raises(MigrationError):
        validate_approval(approval, {**reviewed, "target": "different"})
    (tmp_path / "backup").write_bytes(b"changed")
    with pytest.raises(MigrationError):
        validate_approval(approval, reviewed)


@pytest.mark.parametrize(
    "field", ["approved", "restore_verified", "role_seeds_verified"]
)
def test_approval_requires_explicit_attestations(tmp_path, field):
    reviewed = {"target": "synthetic"}
    approval = _approval(tmp_path, reviewed)
    approval[field] = False
    with pytest.raises(MigrationError):
        validate_approval(approval, reviewed)


def test_stale_or_naive_approval_cannot_authorize_schema_write(tmp_path):
    reviewed = {"target": "synthetic"}
    approval = _approval(tmp_path, reviewed)
    for value in (
        (datetime.now(UTC) - timedelta(days=2)).isoformat(),
        datetime.now().isoformat(),
    ):
        approval["approved_at"] = value
        with pytest.raises(MigrationError):
            validate_approval(approval, reviewed)


def test_missing_prefix_or_corrupt_checkpoint_is_refused():
    migrations = [
        Migration("001", "a", ("one", "two")),
        Migration("002", "b", ("three",)),
    ]
    validate_history(
        {"001": ("a", "APPLIED", 2), "002": ("b", "APPLYING", 0)}, migrations
    )
    for history in (
        {"002": ("b", "APPLIED", 1)},
        {"001": ("a", "APPLIED", 1)},
        {"001": ("a", "APPLYING", -1)},
        {"001": ("a", "INVALID", 0)},
        {"001": ("a", "APPLYING", 1), "002": ("b", "APPLIED", 1)},
    ):
        with pytest.raises(MigrationError):
            validate_history(history, migrations)
