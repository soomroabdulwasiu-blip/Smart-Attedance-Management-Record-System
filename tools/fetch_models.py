"""Download public model assets and accept only the manifest's exact bytes."""

import argparse
import hashlib
import json
import os
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fetch_model(model, destination, opener=urllib.request.urlopen):
    directory = destination.resolve()
    name = model["filename"]
    if Path(name).name != name or not name.endswith(".onnx"):
        raise ValueError("Invalid model filename")
    if not model["url"].startswith(
        "https://media.githubusercontent.com/media/opencv/opencv_zoo/"
    ):
        raise ValueError("Unexpected model source")
    target = directory / name
    if target.is_symlink():
        raise ValueError("Model target must not be a symbolic link")
    directory.mkdir(parents=True, exist_ok=True)
    if (
        target.is_file()
        and hashlib.sha256(target.read_bytes()).hexdigest() == model["sha256"]
    ):
        return "already verified"
    handle, temporary = tempfile.mkstemp(prefix=".download-", dir=directory)
    try:
        digest = hashlib.sha256()
        count = 0
        with (
            os.fdopen(handle, "wb") as output,
            opener(model["url"], timeout=30) as response,
        ):
            while block := response.read(1024 * 1024):
                count += len(block)
                if count > model["size"]:
                    raise ValueError("Model exceeds expected size")
                digest.update(block)
                output.write(block)
        if count != model["size"] or digest.hexdigest() != model["sha256"]:
            raise ValueError("Model checksum/size mismatch; existing model preserved")
        os.replace(temporary, target)
        return "downloaded and verified"
    finally:
        Path(temporary).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=ROOT / "models")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "models" / "manifest.json").read_text())
    for model in manifest["models"]:
        print(model["filename"] + ": " + fetch_model(model, args.destination))


if __name__ == "__main__":
    main()
