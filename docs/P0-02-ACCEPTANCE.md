# P0-02 implementation checkpoint

Historical checkpoint. The newer master-spec implementation, migrations 004–005, explicit adoption verification and current test counts are recorded in TESTING_REPORT.md. Production adoption remains approval-gated.

2 November 2026. Branch: `codex/p0-02-reproducible-db`.

## Verified on this computer

- Native Oracle service and listener are running. SQLPlus OS authentication succeeded, without opening saved credentials.
- A new randomly named schema owner and separate runtime user were created solely for each test invocation, then removed after the checks.
- All 13 application tables, the attendance summary view, indexes, update trigger and role seeds were created from the ordered SQL scripts. The migration registry is an additional table.
- Running migrations again made no changes. A synthetic department row survived the forward workflow-to-recovery migration.
- A changed historical checksum was refused. A deliberately failed synthetic forward migration retained its checkpoint and resumed successfully after the test dependency was supplied.
- The first-admin wizard refused a repeated bootstrap. No administrator password is seeded in source.
- The separate runtime user performed normal database/recovery operations but CREATE TABLE failed with ORA-01031, as expected.
- The isolated test run passed **70 pytest cases**, including the 16 Oracle recovery cases. Historical standalone scenarios are run separately and reported separately from this count.
- The final additional run passed **10 standalone scenarios**, with **0 failures**. These cover teacher/student dashboard metrics and responsive navigation, record lifecycle, manual-preservation behavior, Oracle workflows, QR database writes, QR security/TLS, approval/correction requests, session roster and signup/login forms.
- The dashboard scenario exposed horizontal overflow on the face-attendance page at 950x650. Camera source and actions now use separate rows, with two columns for action buttons and a shrinkable aspect-preserving preview. The unchanged responsive-navigation assertion passed after the fix.
- Native connectivity was checked through the separate runtime account using SELECT from DUAL and CURRENT_SCHEMA verification. The final runner exited successfully and removed both disposable users.
- Ruff checks passed on the new migration/bootstrap/native-test modules and wrappers. Mypy passed on six new source files. The source secret scan reported no leaks with full redaction enabled.
- No production records, private biometric files, stored credentials or mail configuration were read or changed.

## Not yet accepted / not deployed

- Docker container execution is deferred by the owner's explicit native-only instruction. No WSL installation or Windows component change is authorized. No existing collected test depends on Docker; the container deployment check itself remains unrun.
- Six historical biometric scenarios require private face/model fixtures and were not run. These are fixture restrictions, not Docker restrictions. Synthetic face-worker tests do not establish real-camera recognition accuracy or university-scale performance.
- Original legacy-schema adoption still requires a reviewed metadata comparison and backup/restore procedure. The new runner safely refuses an unversioned legacy schema rather than guessing compatibility or changing production tables.
- This branch must remain separate from local main until the outstanding acceptance gates are met or the owner explicitly revises those gates. Phase 1 has not started.

The working installed prototype has not been switched to this new migration contract.
