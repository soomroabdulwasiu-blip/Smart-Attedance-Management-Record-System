"""Separate immutable application resources from per-user runtime data."""

import os
from pathlib import Path

RESOURCE_ROOT = Path(__file__).resolve().parents[1]


def profile_root() -> Path:
    return Path(
        os.environ.get(
            "AMRS_PROFILE_DIR",
            Path(os.environ.get("LOCALAPPDATA", Path.home())) / "AMRS",
        )
    )


DATA_ROOT = (
    Path(os.environ["AMRS_DATA_DIR"])
    if os.getenv("AMRS_DATA_DIR")
    else profile_root() / "runtime"
)
