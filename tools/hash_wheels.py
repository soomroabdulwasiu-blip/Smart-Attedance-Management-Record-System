"""Create a pip --require-hashes lock for the verified Windows wheelhouse."""

import hashlib
from pathlib import Path

from packaging.utils import canonicalize_name, parse_wheel_filename


def write_lock(pins, wheelhouse, output):
    versions = {
        line.split("==")[0]: line.split("==")[1]
        for line in Path(pins).read_text().splitlines()
        if line.strip()
    }
    hashes: dict[str, list[str]] = {}
    for path in Path(wheelhouse).glob("*.whl"):
        name, version, _, _ = parse_wheel_filename(path.name)
        name = canonicalize_name(name)
        if versions.get(name) != str(version):
            continue
        if path.is_symlink():
            raise ValueError("Wheel symlinks are refused.")
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while data := handle.read(1024 * 1024):
                digest.update(data)
        hashes.setdefault(name, []).append(digest.hexdigest())
    if set(hashes) != set(versions):
        raise ValueError("A pinned dependency is missing its downloaded wheel.")
    lines = ["# Exact runtime lock: Windows x64 / CPython 3.14.", "--only-binary=:all:"]
    for pinned_name, pinned_version in sorted(versions.items()):
        lines.append(
            f"{pinned_name}=={pinned_version} "
            + " ".join("--hash=sha256:" + v for v in sorted(hashes[pinned_name]))
        )
    Path(output).write_text("\n".join(lines) + "\n", encoding="utf-8")
