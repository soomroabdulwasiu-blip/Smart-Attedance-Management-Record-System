# AMRS master specification verification

3 November 2026. Checkout: `C:\Users\USER\Documents\Codex\2026-10-30\ana\work\AMRS_Production`. Branch: `codex/p0-02-reproducible-db`.

## Automated results

| Check | Final measured result |
| --- | --- |
| Main pytest suite, native Oracle enabled | 207 passed, 0 failed, 0 skipped; 16 legacy wrappers deselected for a separate run |
| Collected historical scenarios | 10 passed, 6 skipped, 0 failed |
| Unique total across both suites | 217 passed, 6 unavailable fixture cases |
| Application statement coverage in the native suite | 70.85%; 60% gate passed |
| Scoped Ruff lint/format | Passed for 30 new service/tool source files |
| Scoped mypy, including untyped function bodies | Passed for 30 source files |
| Exact locked runtime dependency audit | 0 known vulnerabilities reported |
| Bandit application scan | 0 high, 13 medium, 1 low findings; see review below |
| Clean runtime install | Exact hashed Windows wheels installed offline into the project `.venv`; pip consistency check passed |
| Public model loading | YuNet/SFace downloads matched pinned hashes; actual models loaded and rejected a blank synthetic frame |
| Windows desktop | Actual admin page opened, Oracle-saved mock source connected, live synthetic frame rendered, capture disconnected and window closed |
| Disposable Oracle cleanup | Successful after main and desktop verification |

The previous baseline was 70 pytest cases plus 10 standalone scenarios. Those are not retroactively described as 80 pytest cases. The historical scripts now have explicit pytest wrappers with isolated subprocess execution; they retain their separate result file and six unavailable biometric cases. Focused configuration/UI/source-boundary retests after the full run passed; repeat executions are not added to the unique total above.

## Scope exercised

Fresh schemas applied migrations 001–005, including the 18 application tables, view, trigger, constraints and indexes, plus the migration registry. Forward preservation, repeated no-op migration, historical checksum refusal, malformed-history refusal, first-admin repeat refusal, runtime CREATE TABLE denial, append-only runtime audit grants and interrupted-migration recovery passed. A separate disposable reference schema supported exact metadata comparison and registry-only adoption. Missing approval, mismatched backup evidence, schema drift and repeat adoption were refused; synthetic rows remained intact.

Role/login/signup, teacher approval, authorization, date filters, attendance settings, correction windows, optimistic manual edits and duplicate FACE/QR behavior were exercised. Oracle 26ai can report missing object privileges as ORA-41900; the audit-denial test accepts that specific denial and ORA-01031 from other releases, and still requires the operation to fail. [Oracle error reference](https://docs.oracle.com/en/error-help/db/ora-41900/).

New Oracle scenarios verified device save/list/activation/disable/remove, credential encryption and non-secret persistence, role restrictions, class assignment and mismatched-semester refusal, grouping removal preserving attendance, consent/encrypted templates/revocation, backup-bound maintenance preserving active attendance, and all role pages at 950×650, 1280×720, 1366×768 and 1920×1080.

The multi-face Oracle scenario used two synthetic enrolled identities and a third unknown representation with a real MockCameraAdapter and the normal CameraWorker/Oracle write pipeline. Both authorized student records were saved once and confirmed; unknown detection remained red. This is a deterministic pipeline check, not a measured face-recognition accuracy result.

The face decision tests also cover a malformed detection alongside valid known/unknown faces and float32 confidence rounding at the valid cosine boundary. These cases preserve independent attendance processing and valid bounded scores.

Other adapter tests exercised local discovery, frame validation, HTTP fragment parsing/authentication/redirect refusal, timeout parameters, recovery limits, cancellation, switching and release. Hardware UI tests used Qt workers and an in-memory repository; native scenarios separately verified the real Oracle repository.

## Failures found and corrected

- Oracle metadata comparison required USER_TAB_COLS for virtual-column metadata on this installation. The adoption helper was corrected and then passed native verification.
- Device-type SQL validation was aligned with the adapter enum. Disabling the selected camera now clears selection atomically in the same UPDATE/MERGE, satisfying the active/enabled constraint.
- Admin course controls and field captions overflowed at the minimum width. Action layouts/caption wrapping were corrected without relaxing the no-horizontal-overflow assertion.
- Background dashboard jobs could outlive a test/window close and interfere with a later substituted repository. Sign-out now waits responsively for outstanding operations; the cache test isolates earlier workers before validating exactly one query.
- Missing-object privilege errors differed in Oracle 26ai; the test was updated to the documented specific error code, retaining its denial assertion.
- An unrelated ICU library from a developer tool's PATH entered the first portable bundle, causing QtCore startup failure. The corrected build recipe excludes those conflicting unversioned libraries and uses the Windows ICU API. Final portable results are recorded in the delivery manifest.
- Dependency audit initially returned 23 advisory entries, including duplicates, across five old packages. Certifi, Flask, Requests, urllib3 and Werkzeug were patched in the development environment; the exact locked set then reported zero known vulnerabilities. The working Downloads environment was not patched by this work.

The final source startup smoke passed three consecutive executions. The final portable executable exited successfully (code 0, 10.1 seconds in this local offscreen smoke), and all 36 recorded source/SQL/lock hashes matched the final checkout. Explicit Qt widget/application cleanup was added after an intermittent teardown failure; this does not establish clean-machine behavior.

The owner confirmed that a production backup is not yet available. Production adoption/migration was therefore not applied; the separate Downloads installation remains untouched.

## Security scan review

The 13 medium Bandit findings concern SQL assembled with fixed, role-selected predicates/table/column names. The identifiers are selected from source constants; user values remain Oracle binds. These findings were inspected and were not hidden with broad scanner exclusions. The low finding is the existing best-effort reset-notification failure path. The CI high-severity gate passes; this is not an external penetration-test claim or a statement that future security work is finished.

The hash lock was made from the exact downloaded Windows wheels and verified through a clean offline install. The initial general hash-resolver attempt was not used as release evidence. The checked-in wheel-lock utility records/verifies all pinned runtime wheels. Dependency audits are time-bound observations, not permanent safety guarantees.

## Unavailable checks and remaining acceptance

The following scripts were collected and explicitly skipped because authorized private biometric fixtures were not available: admin_new_integration.py, admin_ui_integration.py, camera_completion_integration.py, face_oracle_integration.py, group_integration.py and known_unknown_integration.py. No protected photo/template was opened to make them pass. These skips are unrelated to Docker.

Physical USB/IP/Pi/ESP32 devices, a real group of consenting students, lighting/distance/bias/liveness evaluation, live Gmail delivery, production backup/restore/adoption, code signing, hosted CI and clean-machine distribution remain unverified. The local architecture and course/day attendance granularity have the production limits described in DEPLOYMENT.md. No WSL, Windows component, production record or production credential was changed.

## Evidence

Ignored local artifacts contain native-pytest.xml, native-legacy.xml, native-summary.json, legacy-results.json, coverage-native.json, coverage.xml, desktop-native-summary.json, desktop-hardware.png, pip-audit-final.json, bandit-app-final.json, clean-runtime-install.log and portable startup/build reports. Generated credentials and child exception values are not copied into the engineering report.
