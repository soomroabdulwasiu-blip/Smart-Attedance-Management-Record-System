# P0-01 acceptance checkpoint

Date: 2 November 2026

## Evidence

- Source imported from an explicit file allowlist, excluding private data/configuration, virtual environments and binaries.
- Original application source baseline: 32 passed, 16 skipped, 0 failed. A pytest cache write warning was environmental.
- Clean source checkout with hygiene tests: 49 passed, 16 skipped, 0 failed.
- A separate fresh Git clone: 49 passed, 16 skipped, 0 failed.
- Gitleaks 8.30.1 official Windows archive matched its published checksum. Source and Git-history scans reported no leaks. Findings were configured for full redaction.
- The tracked-file boundary accepted 64 initial source files. The source archive included a SHA-256 manifest and excluded private runtime directories, local credentials, model binaries and environments.
- Model-downloader tests cover size/hash rejection, preservation of an earlier model, temporary-file cleanup and idempotent reuse of verified bytes. Public model downloads were not run against production model files.
- Ruff checks/format and mypy checks cover the new developer-tool modules. This is not a claim that legacy application code already passes a repository-wide static-quality policy.

## Remaining phase work and limits

- P0-01 adds a pinned pre-commit hook and GitHub Actions source-hygiene workflow. No remote repository exists yet and no hosted pipeline run is claimed. Developers install the hook as described in SOURCE_RELEASE.md.
- Oracle integration cases remain skipped. No production database, credentials or biometric files were used.
- P0-02 is not complete: a full reproducible schema/migration runner and an isolated Oracle test environment are still required.
- Docker CLI exists, but its Linux engine was unavailable during the check. Do not silently change Windows/WSL features or connect test jobs to the production database as a workaround.
- No database migration, purge, package installer, server API or new academic rule has been deployed by this work package.

The clean checkout is the development baseline. The installed application remains the owner's working prototype until subsequent packages are accepted and an explicit validated upgrade is ready.
