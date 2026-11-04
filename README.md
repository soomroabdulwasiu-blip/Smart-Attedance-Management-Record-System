<<<<<<< HEAD
# AMRS desktop attendance

Continue development in this checkout. Python 3.14 x64, PySide6 and native Oracle remain the application stack. The separate Downloads installation has not been replaced.

Run from VS Code PowerShell:

```powershell
.\.venv\Scripts\python.exe main.py
```

The first-run Oracle connection form verifies an already migrated schema and can remember runtime credentials using Windows-user encryption. It does not create users or migrate a working database automatically. No default administrator password is included.

- [Windows setup and exact commands](docs/WINDOWS_STARTUP.md)
- [Oracle provisioning, migrations and approval-gated legacy adoption](docs/DATABASE_SETUP.md)
- [Administrator, teacher and student workflows](docs/USER_GUIDE.md)
- [Camera adapters, simulation and physical acceptance](docs/HARDWARE_INTEGRATION.md)
- [Security boundaries](docs/WORKFLOW_SECURITY.md)
- [Source release boundary](docs/SOURCE_RELEASE.md)
- [Deployment and remaining acceptance](docs/DEPLOYMENT.md)

New capabilities include Oracle-persisted camera configuration, an administrator hardware page and setup wizard, local/USB/RTSP/HTTP/Raspberry Pi/ESP32 stream adapters, bounded reconnection, labelled simulation, class/section grouping, audit events, consent-controlled encrypted face representations, background read/write workflows, date-filtered history and safe diagnostics export. Existing teacher approval, student login, face/manual/QR attendance and correction/reporting workflows are preserved.

Use `requirements.lock.txt` with `--require-hashes` for the verified Windows/Python runtime. Development tools are installed separately using `requirements-dev.txt` after that lock. Public models are fetched using `tools/fetch_models.py`; personal face images and saved credentials are never included in the source release.

`python purge_inactive_records.py` now previews only. Execution needs explicit confirmation, administrator authentication and a fresh backup/restore approval tied to the exact preview. Do not run production cleanup during setup.

This is an integration-tested development/pilot candidate, not a production certification. Physical classroom accuracy, liveness protection, cross-user/server biometric custody, real hardware acceptance, live Gmail delivery, signed deployment and institutional governance are not established merely by automated tests. See the final engineering/testing report for measured results and remaining limits.
=======
# Smart-Attedance-Management-Record-System
Smart Attendance Management Record System (AMRS) is a secure desktop application featuring multi-face recognition, QR code-based attendance with facial verification, manual attendance, role-based dashboards, course management, real-time email password recovery, and attendance reporting.
>>>>>>> 2871bb6f8e14301698ab02e68bbd7e82e471f783
