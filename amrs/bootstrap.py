"""Interactive first administrator setup. No default password is stored or printed."""

import argparse
import getpass
import os
import sys
import uuid

import oracledb

from .db import hash_password
from .mail_delivery import valid_email
from .migrations.runner import MigrationError, require_current


def create_admin(connection, name, email, password, department):
    require_current(connection)
    email = valid_email(email)
    if not name.strip() or not department.strip():
        raise ValueError("Name and initial department are required.")
    digest = hash_password(password)
    cur = connection.cursor()
    cur.execute("LOCK TABLE users IN EXCLUSIVE MODE WAIT 5")
    cur.execute(
        "SELECT COUNT(*) FROM users u JOIN roles r ON r.role_id=u.role_id WHERE r.role_name='ADMIN'"
    )
    if cur.fetchone()[0]:
        raise ValueError("An administrator already exists. First-run setup refused.")
    cur.execute(
        "INSERT INTO departments(dept_name) VALUES(:name)", {"name": department.strip()}
    )
    cur.execute(
        "INSERT INTO users(user_id,full_name,email,password_hash,role_id) VALUES(:id,:name,:email,:pw,(SELECT role_id FROM roles WHERE role_name='ADMIN'))",
        {"id": str(uuid.uuid4()), "name": name.strip(), "email": email, "pw": digest},
    )
    connection.commit()


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        name = input("Administrator name: ")
        email = input("Administrator login email: ")
        department = input("Initial department name: ")
        password = getpass.getpass("New administrator password: ")
        if password != getpass.getpass("Confirm password: "):
            raise ValueError("Passwords do not match.")
        with oracledb.connect(
            user=os.environ["AMRS_MIGRATION_USER"],
            password=os.environ["AMRS_MIGRATION_PASSWORD"],
            dsn=os.environ["AMRS_MIGRATION_DSN"],
        ) as c:
            create_admin(c, name, email, password, department)
        print("First administrator created. No default credentials were used.")
        return 0
    except (ValueError, MigrationError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (oracledb.Error, KeyError, OSError):
        print(
            "Setup failed. Check the dedicated migration connection and schema state.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
