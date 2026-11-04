"""Create a clean source ZIP from an explicit, Git-tracked file allowlist."""

import argparse
import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
TOP = {
    "AMRS-QR-Trust.cer",
    "FILE_MANIFEST.json",
    "main.py",
    "README.md",
    "START_HERE.txt",
    "CHANGELOG.md",
    "requirements.txt",
    "requirements-dev.txt",
    "requirements.in",
    "requirements.lock.txt",
    "pyproject.toml",
    "tools/amrs.spec",
    "run.bat",
    "run_local.bat",
    "setup.bat",
    "oracle-local.example.bat",
    "migrate_workflows.py",
    "migrate_email_recovery.py",
    "purge_inactive_records.py",
    ".gitignore",
    ".gitleaks.toml",
    ".pre-commit-config.yaml",
    ".env.example",
}


def allowed(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
        return False
    if name in TOP:
        return True
    if (
        len(path.parts) == 3
        and path.parts[:2] == ("db", "schema")
        and path.suffix == ".sql"
    ):
        return True
    if name == "models/manifest.json":
        return True
    if name in {"amrs/qr_assets/index.html", "amrs/qr_assets/checkin.css", "amrs/qr_assets/checkin.js"}:
        return True
    if len(path.parts) > 1 and path.parts[0] in {"amrs", "tests", "tools"}:
        return path.suffix == ".py" and "__pycache__" not in path.parts
    if (
        len(path.parts) == 2
        and path.parts[0] == "Offline_Wheels"
        and path.suffix == ".whl"
    ):
        return True
    if len(path.parts) > 1 and path.parts[0] == "docs":
        return path.suffix == ".md"
    return (
        len(path.parts) == 3
        and path.parts[:2] == (".github", "workflows")
        and path.suffix in {".yml", ".yaml"}
    )


def checked_paths(root, names):
    paths = []
    for name in sorted(names):
        if not allowed(name):
            raise ValueError("Tracked file outside release allowlist; release refused")
        path = root / name
        if not path.is_file() or any(
            p.is_symlink() for p in [path, *path.parents] if p != root.parent
        ):
            raise ValueError(
                "Release inputs must be regular files without symbolic links"
            )
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Release input escapes repository")
        paths.append((name, path))
    return paths


def tracked_paths(root):
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"], check=True, capture_output=True
    )
    return (
        result.stdout.decode("utf-8").rstrip("\0").split("\0") if result.stdout else []
    )


def write_archive(paths, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    records = []
    # Refuse overwrites and include only names checked before reading any file bytes.
    with zipfile.ZipFile(output, "x", zipfile.ZIP_DEFLATED) as archive:
        for name, path in paths:
            data = path.read_bytes()
            archive.writestr(name, data)
            records.append({"path": name, "sha256": hashlib.sha256(data).hexdigest()})
        archive.writestr("SOURCE_MANIFEST.json", json.dumps(records, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--gitleaks", default=shutil.which("gitleaks"))
    args = parser.parse_args()
    paths = checked_paths(ROOT, tracked_paths(ROOT))
    if not paths:
        parser.error("No tracked source files")
    if args.check_only:
        print(f"PASS: {len(paths)} tracked files satisfy release boundary")
        return
    if args.output is None or not args.gitleaks:
        parser.error("--output and an available gitleaks scanner are required")
    # Scan history AND current tracked working files. Do not scan private working-tree data.
    subprocess.run(
        [args.gitleaks, "git", "--redact=100", "--no-banner", str(ROOT)], check=True
    )
    import tempfile

    with tempfile.TemporaryDirectory(prefix="amrs-source-scan-") as temporary:
        scan = Path(temporary)
        for name, path in paths:
            target = scan / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())
        subprocess.run(
            [args.gitleaks, "dir", "--redact=100", "--no-banner", str(scan)], check=True
        )
        write_archive(
            checked_paths(scan, [name for name, _ in paths]), args.output.resolve()
        )
    print(f"Clean source archive created: {args.output.name}")


if __name__ == "__main__":
    main()
