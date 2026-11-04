# Source repository and release boundary

This is a clean development checkout of the AMRS prototype. Only an explicit source-file list was copied from the working application. No private data/configuration directory, virtual environment, stored credentials, model binary, database export or existing ZIP was copied. The working installation remains separate.

## What a clean clone contains

Application/test Python files, launch examples, sanitized configuration templates, documentation, migration wrappers, developer tools, public model metadata and source-hygiene workflow configuration. It does not contain a working database, default administrator password, trained personal face references, downloaded models or an installer.

Do not make or distribute a recursive ZIP of a working application directory. Git ignores are not a security boundary for arbitrary ZIP tools.

## Checks before committing

Install `pre-commit` in a developer environment and run `pre-commit install`, followed by `pre-commit run --all-files`. The hook pins Gitleaks v8.30.1. Do not disable its default rules or add broad path exclusions to hide a finding. Scanner output must be redacted.

The GitHub Actions source-hygiene workflow scans complete Git history and checks tracked paths. It will run only after an authorized remote is configured; a checked-in workflow is not proof of a successful hosted run.

## Models

Run `python tools/fetch_models.py` to fetch public YuNet/SFace weights. Downloads are accepted only when their byte size and SHA-256 match `models/manifest.json`. A checksum failure preserves an existing file. The downloader is not an updater: an upstream change requires a reviewed manifest change and regression tests. License review and distribution notices remain required before commercial packaging.

Official pointers used for the manifest:
- https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
- https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx
- https://github.com/gitleaks/gitleaks/releases/tag/v8.30.1

## Creating a source ZIP

Stage/commit intended source changes, then run:

```powershell
python tools/release_source.py --check-only
python tools/release_source.py --output artifacts/AMRS-source.zip --gitleaks <path-to-gitleaks>
```

The builder refuses tracked files outside its allowlist. It scans history and a source-only snapshot with redacted findings, writes only permitted files, includes a SHA-256 file manifest and refuses to overwrite an existing ZIP. Keep source packages separate from runtime/installer artifacts. Models are intentionally downloaded separately.

The development branch includes the complete new-install schema, versioned migrations, explicit metadata-only legacy adoption and encrypted first-run runtime setup. Actual production adoption still requires the owner's approval and verified backup/restore. Maintenance defaults to a read-only preview, with a separate explicit approval gate for execution. See TESTING_REPORT.md and DEPLOYMENT.md for current verification and limits.

