import pytest

from amrs.migrations.runner import MigrationError, read_migrations
from tools.grant_runtime import grant_runtime


def test_migration_inventory_has_unique_order_and_no_seeded_admin():
    migrations = read_migrations()
    assert [m.version for m in migrations] == ["001", "002", "003", "004", "005"]
    text = "\n".join(s for m in migrations for s in m.statements).lower()
    assert text.count("create table ") == 18
    assert "insert into users" not in text
    assert all(len(m.checksum) == 64 for m in migrations)


def test_checksums_ignore_checkout_line_endings_but_detect_content_changes(tmp_path):
    p = tmp_path / "001_test.sql"
    p.write_bytes(b"CREATE TABLE example(id NUMBER)\r\n/\r\n")
    first = read_migrations(tmp_path)[0].checksum
    p.write_bytes(b"CREATE TABLE example(id NUMBER)\n/\n")
    assert read_migrations(tmp_path)[0].checksum == first
    p.write_text("CREATE TABLE example(id VARCHAR2(10))\n/\n")
    assert read_migrations(tmp_path)[0].checksum != first


def test_duplicate_versions_refuse_before_connection(tmp_path):
    for name in ("001_one.sql", "001_two.sql"):
        (tmp_path / name).write_text("SELECT 1 FROM dual\n/\n")
    with pytest.raises(MigrationError):
        read_migrations(tmp_path)


def test_grant_identifiers_are_validated_before_sql():
    with pytest.raises(ValueError):
        grant_runtime(None, "INVALID; DROP USER x")


def test_release_boundary_includes_only_schema_sql():
    from tools.release_source import allowed

    assert allowed("db/schema/001_base.sql")
    assert not allowed("db/schema/backup.dmp")
    assert not allowed("db/schema/credentials.bat")
