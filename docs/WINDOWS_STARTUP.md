# Run the development application in VS Code

Use this checkout, not the separate Downloads installation:

```powershell
Set-Location 'C:\Users\USER\Documents\Codex\2026-10-30\ana\work\AMRS_Production'
.\.venv\Scripts\python.exe main.py
```

The project-local `.venv` has been created from the Windows x64 / Python 3.14 runtime lock. In VS Code, use **Python: Select Interpreter → Enter interpreter path** and select `.venv\Scripts\python.exe` inside this checkout. Activation is optional; the explicit command above works without changing PowerShell execution policy. `run.bat` also uses this environment and no longer executes saved Oracle batch files.

On first launch, enter the separately provisioned runtime account, application owner/schema, service address such as `localhost:1521/FREEPDB1`, and runtime password in **Oracle connection setup**. Select **Remember securely** to encrypt the credentials for this Windows user. Future launches load that setup automatically. This is the database connection, not the administrator/teacher/student login. Never share passwords in chat or enter them as command-line arguments.

The first administrator is created by the existing interactive bootstrap wizard after DBA setup. No administrator login or password is seeded in source. See DATABASE_SETUP.md. If the working legacy schema is unversioned, this application must not automatically migrate it: a reviewed adoption plan, verified backup/restore and explicit approval are required first.

## Clean setup on another Windows computer

Install Python 3.14 x64, open the source folder in PowerShell and run:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock.txt
.\.venv\Scripts\python.exe tools/fetch_models.py
.\.venv\Scripts\python.exe main.py
```

The lock is intentionally for Windows x64 / CPython 3.14. Other Python versions/platforms have not been validated. Models are public downloads checked against pinned SHA-256 hashes. A supplied offline runtime wheelhouse can be used with `--no-index --find-links <wheelhouse>`; the same hashes remain mandatory.

For development checks, install tools separately after the locked runtime:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest tests -m 'not legacy' -q
```

Without the disposable Oracle runner, Oracle cases are skipped. Never point integration tests at the working schema. The native runner creates and removes only generated test accounts:

```powershell
$env:AMRS_ALLOW_NATIVE_ISOLATED_TEST = '1'
$env:AMRS_TEST_SQLPLUS = 'C:\app\USER\product\26ai\dbhomeFree\bin\sqlplus.exe'
.\.venv\Scripts\python.exe -m tools.native_oracle_check
```

This last command needs an already authorized SQLPlus OS-authenticated development shell. It is a test-administration operation; it does not install Oracle, WSL or Windows components. See the test report for exactly what it verifies.

## Common startup problems

- **Missing environment:** recreate `.venv` and install the lock; select that interpreter in VS Code.
- **Oracle listener/service unavailable:** start the existing Oracle service through the administrator's normal procedure; verify the configured PDB/service. The application does not change Windows services/firewall rules.
- **Database setup needed:** follow DATABASE_SETUP.md with a DBA. Login does not run DDL.
- **Models missing:** run `tools/fetch_models.py`. No face images are downloaded or copied.
- **Camera unavailable:** close other camera apps, check Windows camera permissions, and test the source in Hardware & cameras. Raw network URLs are configured by the administrator, then selected by the teacher.
- **Encrypted settings cannot be opened:** Windows DPAPI binds secrets/templates to the original Windows user. Reconfigure authorized credentials or re-enroll with consent; copying encrypted files to a different user does not transfer access.

## Safe configuration and maintenance

Optional non-secret settings are in `%LOCALAPPDATA%\AMRS\config.json`; supported typed fields are declared in `amrs/config.py`. Environment variables override this file. Passwords are rejected in that file and belong in the encrypted setup. Runtime files live under `%LOCALAPPDATA%\AMRS\runtime`; no existing face/photo directory is copied automatically.

`python purge_inactive_records.py` is a read-only preview by default. Destructive cleanup additionally requires `--confirm`, administrator authentication and a fresh, plan-bound backup/restore approval. Do not execute it on production as part of installation.
