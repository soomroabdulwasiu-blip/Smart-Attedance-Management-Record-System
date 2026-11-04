"""Build an unsigned portable Windows app from public, verified resource files."""

import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    if os.name != "nt":
        raise RuntimeError("Build the Windows application on Windows.")
    # Verify model files against the same public release manifest before packaging.
    manifest = json.loads((ROOT / "models" / "manifest.json").read_text())
    models = manifest["models"] if isinstance(manifest, dict) else manifest
    for model in models:
        path = ROOT / "models" / model["filename"]
        if (
            Path(model["filename"]).name != model["filename"]
            or path.suffix != ".onnx"
            or path.is_symlink()
        ):
            raise ValueError("Only explicit public model files can be bundled.")
        data = path.read_bytes()
        if (
            len(data) != model["size"]
            or hashlib.sha256(data).hexdigest() != model["sha256"]
        ):
            raise ValueError("Public model checksum verification failed.")
    output = (
        ROOT / "artifacts" / ("windows-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S"))
    )
    output.mkdir(parents=True, exist_ok=False)
    sources = [
        ROOT / "main.py",
        ROOT / "requirements.lock.txt",
        *sorted((ROOT / "amrs").rglob("*.py")),
        *sorted((ROOT / "db" / "schema").glob("*.sql")),
    ]
    if any(path.is_symlink() for path in sources):
        raise ValueError("Build sources must not be symlinks.")
    build_manifest = {
        "target": "Windows x64 / CPython 3.14",
        "unsigned": True,
        "source_sha256": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sources
        },
        "models_sha256": {model["filename"]: model["sha256"] for model in models},
    }
    metadata = output / "BUILD_MANIFEST.json"
    metadata.write_text(json.dumps(build_manifest, indent=2), encoding="utf-8")
    args = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--distpath",
        str(output / "dist"),
        "--workpath",
        str(output / "build"),
        str(ROOT / "tools" / "amrs.spec"),
    ]
    result = subprocess.run(
        args,
        cwd=ROOT,
        env=dict(os.environ, AMRS_BUILD_MANIFEST=str(metadata)),
        check=False,
    )
    if result.returncode:
        return result.returncode
    print("Portable development build: " + str(output / "dist" / "AMRS" / "AMRS.exe"))
    print(
        "Unsigned build; real hardware, institution acceptance and clean-machine testing remain required."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
