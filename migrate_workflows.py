"""Compatibility wrapper for the versioned migration CLI."""

from amrs.migrate import main


def migrate():
    return main(["up"])


if __name__ == "__main__":
    raise SystemExit(migrate())
