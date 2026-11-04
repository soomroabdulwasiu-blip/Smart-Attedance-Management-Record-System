# Windows deployment and acceptance

The current source is ready for integration testing. A portable Windows build is produced from the clean project virtual environment; it is unsigned. It is not a production certification or a replacement of the working Downloads installation.

## Build and launch

```powershell
.\.venv\Scripts\python.exe -m tools.build_windows
```

The command verifies public model hashes, creates a fresh timestamped directory under `artifacts/windows-*`, records source/SQL/model SHA-256 values in BUILD_MANIFEST.json, and runs the checked-in `tools/amrs.spec`. The output is `dist/AMRS/AMRS.exe`. Keep the complete AMRS folder together; copying only the executable omits required libraries/resources. Runtime data and encrypted credentials use the Windows user's AMRS directory, outside the application bundle.

The build recipe excludes unversioned ICU libraries that an unrelated developer tool might expose through PATH. An actual diagnostic build established that such a library caused the QtCore import failure on this computer; allowing Qt to use the Windows-provided ICU API fixed startup. No Windows file is replaced or modified. Dependency metadata is bundled so diagnostics can identify runtime versions.

Use the one-time Oracle setup form with the restricted runtime account and an already migrated owner/schema. Set up the first administrator using the existing bootstrap contract. There are no production default login credentials and no automatic migration at application startup.

## Required before supervised pilot

1. Obtain explicit approval, a verified backup and a successful restore rehearsal before changing the working schema. Review the metadata-only adoption plan. Exact compatible prefixes can be baselined; divergent schemas are refused for manual DBA review.
2. Provision a separate pilot owner/runtime account and review Oracle grants. Do not use SYSTEM as an application runtime account.
3. Configure institutional HTTPS for QR and authorized mail delivery. Confirm the real reset email in the approved recipient inbox. SMTP acceptance alone does not establish inbox delivery.
4. Record institutional consent/retention rules. New templates and camera secrets use Windows-user encryption; a server deployment requires server-side custody and authorization design.
5. Perform the physical acceptance procedures in HARDWARE_INTEGRATION.md using consenting participants. Measure false accepts/rejects, throughput and user feedback at real classroom distances/lighting. Include unknowns and multiple faces. Do not infer 10–20-person accuracy from synthetic vectors.
6. Validate the complete portable build on a separate supported Windows computer with the target Oracle/network/camera environment, and review dependency/model licenses and notices. Obtain a code-signing certificate and institution deployment approval before distributing a signed installer.

## Verified versus pending

- **Implemented and locally verified:** Oracle migrations/adoption guards, runtime DDL/audit restrictions, account/approval workflows, manual/QR attendance, scoped reports, class grouping, device persistence, mock camera lifecycle, synthetic multi-face Oracle persistence, Qt workflows/layouts and source/dependency checks. See TESTING_REPORT.md for counts and scope.
- **Implemented, awaiting physical acceptance:** laptop/USB adapters and compatible RTSP/HTTP/Pi/ESP32 streaming adapters. No device purchase, driver installation, Pi OS change or board flash was performed.
- **Partially implemented / deployment limits:** role checks are application-level over a shared restricted runtime account; this local pilot is not a hardened client/server security boundary. The original attendance key remains course/student/date, so independent multiple lectures of the same course on the same date need the future explicit-session domain model. Institutional retention automation, server-side matching/custody, broader role hierarchy and load/SLA validation remain future production work.
- **Not verified:** live Gmail delivery, private biometric-fixture scenarios, physical group accuracy/liveness, clean-machine deployment, signing and hosted CI. No liveness/anti-spoofing protection is claimed.
- **Deferred by owner:** Docker/container verification; WSL installation and Windows component changes are prohibited for this work.

The Windows CI workflow is source configuration, not evidence of a hosted run. It provides Windows unit checks, a camera-boundary coverage gate, type/security checks and an explicit-dispatch native Oracle job for an already authorized isolated self-hosted test runner. No remote repository or runner was configured automatically.
