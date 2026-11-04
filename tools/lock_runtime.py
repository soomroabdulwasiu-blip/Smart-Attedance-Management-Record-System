"""Resolve a hashed runtime lock constrained to the versions verified locally."""

import subprocess
import sys
from importlib.metadata import distribution
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]


def main():
    pending = [
        Requirement(line)
        for line in (ROOT / "requirements.in").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    found: dict[str, str] = {}
    extras: dict[str, set[str]] = {}
    while pending:
        requirement = pending.pop()
        name = canonicalize_name(requirement.name)
        wanted = set(requirement.extras)
        if name in found and wanted.issubset(extras.get(name, set())):
            continue
        extras.setdefault(name, set()).update(wanted)
        package = distribution(requirement.name)
        found[name] = package.version
        for raw in package.requires or ():
            child = Requirement(raw)
            if child.marker is None or any(
                child.marker.evaluate({"extra": extra}) for extra in ("", *extras[name])
            ):
                pending.append(child)
    pins = ROOT / "artifacts" / "runtime-installed-pins.txt"
    pins.parent.mkdir(exist_ok=True)
    pins.write_text(
        "\n".join(f"{name}=={version}" for name, version in sorted(found.items()))
        + "\n"
    )
    wheels = ROOT / "artifacts" / "runtime-wheels"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "download",
            "--only-binary=:all:",
            "--no-deps",
            "--index-url",
            "https://pypi.org/simple",
            "--timeout",
            "15",
            "--retries",
            "1",
            "-r",
            str(pins),
            "--dest",
            str(wheels),
        ],
        cwd=ROOT,
        check=False,
        timeout=240,
    )
    if result.returncode:
        return result.returncode
    from tools.hash_wheels import write_lock

    write_lock(pins, wheels, ROOT / "requirements.lock.txt")
    print("Hashed Windows runtime lock generated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
