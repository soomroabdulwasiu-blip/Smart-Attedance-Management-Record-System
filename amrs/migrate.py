"""Administrator CLI: python -m amrs.migrate up (never runs at app startup)."""

import argparse
import json
import os
import sys
from pathlib import Path

import oracledb

from .migrations.runner import MigrationError, apply, read_migrations


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["up", "adopt-plan", "adopt"])
    parser.add_argument(
        "--through", help="Exact already-present legacy migration prefix, e.g. 003"
    )
    parser.add_argument(
        "--plan", type=Path, help="Reviewed redacted adoption plan JSON"
    )
    parser.add_argument(
        "--approval", type=Path, help="Explicit backup/restore approval JSON"
    )
    args = parser.parse_args(argv)
    names = ("AMRS_MIGRATION_USER", "AMRS_MIGRATION_PASSWORD", "AMRS_MIGRATION_DSN")
    if not all(os.getenv(name) for name in names):
        print(
            "Set the dedicated migration user, password and DSN in a secure environment. Runtime credentials are not used.",
            file=sys.stderr,
        )
        return 2
    try:
        with oracledb.connect(
            user=os.environ[names[0]],
            password=os.environ[names[1]],
            dsn=os.environ[names[2]],
        ) as connection:
            if args.command == "up":
                migrations = read_migrations()
                if args.through:
                    selected = [m.version for m in migrations]
                    if args.through not in selected:
                        raise MigrationError("Unknown --through migration version.")
                    migrations = migrations[: selected.index(args.through) + 1]
                versions = apply(connection, migrations)
            else:
                from .migrations.adoption import adopt, fingerprint, plan

                reference_names = (
                    "AMRS_REFERENCE_USER",
                    "AMRS_REFERENCE_PASSWORD",
                    "AMRS_REFERENCE_DSN",
                )
                if not all(os.getenv(name) for name in reference_names):
                    raise MigrationError(
                        "A separate trusted reference schema connection is required through AMRS_REFERENCE_USER/PASSWORD/DSN."
                    )
                if not args.plan:
                    raise MigrationError(
                        "Adoption requires --plan pointing to a reviewed local JSON plan."
                    )
                with oracledb.connect(
                    user=os.environ[reference_names[0]],
                    password=os.environ[reference_names[1]],
                    dsn=os.environ[reference_names[2]],
                ) as reference:
                    if args.command == "adopt-plan":
                        if not args.through:
                            raise MigrationError(
                                "Select the exact source baseline using --through."
                            )
                        if args.plan.exists():
                            raise MigrationError(
                                "Plan already exists; choose a new path to preserve review evidence."
                            )
                        result = plan(connection, reference, args.through)
                        args.plan.write_text(
                            json.dumps(result, indent=2), encoding="utf-8"
                        )
                        print(
                            "Plan written. Compatible: "
                            + str(result["compatible"])
                            + "; plan SHA-256: "
                            + fingerprint(result)
                        )
                        return 0 if result["compatible"] else 1
                    if not args.approval:
                        raise MigrationError(
                            "Adoption requires --approval with verified-backup and restore evidence."
                        )
                    reviewed = json.loads(args.plan.read_text(encoding="utf-8"))
                    approval = json.loads(args.approval.read_text(encoding="utf-8"))
                    versions = adopt(connection, reference, reviewed, approval)
        print(
            "Applied: "
            + (", ".join(versions) if versions else "none; schema already current")
        )
        return 0
    except MigrationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (oracledb.Error, OSError, ValueError, TypeError):
        print(
            "Migration connection failed. Check the dedicated setup account and Oracle service.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
