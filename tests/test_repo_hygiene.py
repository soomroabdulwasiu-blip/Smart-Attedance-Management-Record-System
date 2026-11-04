import hashlib
import io
import zipfile

import pytest

from tools.fetch_models import fetch_model
from tools.release_source import allowed, checked_paths, write_archive


@pytest.mark.parametrize(
    "name",
    [
        "data/faces/private.image",
        "data/mail_setup.json",
        "oracle-local.bat",
        ".env",
        ".venv/Scripts/python.exe",
        "models/private.onnx",
        "../outside.py",
        "amrs/../../outside.py",
        "C:/secret.py",
        "amrs\\secret.py",
        "logs/events.log",
        ".git/config",
    ],
)
def test_private_or_unsafe_paths_are_never_allowed(name):
    assert not allowed(name)


def test_tracked_private_file_refuses_release_before_read(tmp_path):
    # No file is created: the boundary must reject it before inspecting file contents.
    with pytest.raises(ValueError, match="allowlist"):
        checked_paths(tmp_path, ["data/mail_setup.json"])


def test_archive_contains_only_checked_source_and_manifest(tmp_path):
    (tmp_path / "main.py").write_text('print("hello")')
    archive = tmp_path / "source.zip"
    write_archive(checked_paths(tmp_path, ["main.py"]), archive)
    with zipfile.ZipFile(archive) as z:
        assert set(z.namelist()) == {"main.py", "SOURCE_MANIFEST.json"}
        assert z.read("main.py") == b'print("hello")'
    with pytest.raises(FileExistsError):
        write_archive(checked_paths(tmp_path, ["main.py"]), archive)


def test_checksum_failure_preserves_previous_model(tmp_path):
    target = tmp_path / "test.onnx"
    target.write_bytes(b"previous")
    model = {
        "filename": "test.onnx",
        "url": "https://media.githubusercontent.com/media/opencv/opencv_zoo/test",
        "size": 4,
        "sha256": hashlib.sha256(b"good").hexdigest(),
    }
    with pytest.raises(ValueError, match="mismatch"):
        fetch_model(model, tmp_path, lambda *a, **k: io.BytesIO(b"evil"))
    assert target.read_bytes() == b"previous"
    assert not list(tmp_path.glob(".download-*"))


def test_verified_download_and_idempotent_repeat(tmp_path):
    model = {
        "filename": "test.onnx",
        "url": "https://media.githubusercontent.com/media/opencv/opencv_zoo/test",
        "size": 4,
        "sha256": hashlib.sha256(b"good").hexdigest(),
    }
    assert (
        fetch_model(model, tmp_path, lambda *a, **k: io.BytesIO(b"good"))
        == "downloaded and verified"
    )

    def no_network(*args, **kwargs):
        pytest.fail("Verified model should not be downloaded again")

    assert fetch_model(model, tmp_path, no_network) == "already verified"


def test_oversized_download_and_invalid_target_are_rejected(tmp_path):
    model = {
        "filename": "test.onnx",
        "url": "https://media.githubusercontent.com/media/opencv/opencv_zoo/test",
        "size": 4,
        "sha256": hashlib.sha256(b"good").hexdigest(),
    }
    with pytest.raises(ValueError, match="exceeds"):
        fetch_model(model, tmp_path, lambda *a, **k: io.BytesIO(b"oversize"))
    with pytest.raises(ValueError, match="filename"):
        fetch_model(dict(model, filename="../escape.onnx"), tmp_path)
