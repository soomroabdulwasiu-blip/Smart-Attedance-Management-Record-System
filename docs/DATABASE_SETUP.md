# Oracle schema setup and migration operation

## Connections and privileges

Use a fresh dedicated schema for a new installation. Do not run this setup against the working prototype schema. The normal `up` command refuses to adopt unversioned legacy USERS/STUDENTS/ATTENDANCE tables automatically. The separate, explicitly approved adoption procedure below can baseline an exactly compatible schema without rewriting its application rows.

A DBA creates two users with independently generated passwords supplied through a secure interactive channel:

- Schema/migration owner: CREATE SESSION, CREATE TABLE, CREATE VIEW, CREATE TRIGGER, CREATE SEQUENCE; bounded quota on its application tablespace; explicit EXECUTE on SYS.DBMS_LOCK. No DBA, RESOURCE, ANY TABLE, ANY PRIVILEGE or access to another application schema is required.
- Runtime user: CREATE SESSION plus the object privileges produced by `tools.grant_runtime.grant_runtime(owner_connection, runtime_username)`. Read-only access to roles/departments, summary view and migration registry; application-table DML for the existing workflows, devices, consents, settings and academic classes. The app_audit table receives SELECT/INSERT only, without UPDATE/DELETE. No DDL/system administrator privileges.

DBA provisioning is separate from application migrations and is not run automatically. Never place either password in source, a command-line argument, a checked-in file, a screenshot or a log. No hard-coded administrator password is included.

## Initial installation

1. Set `AMRS_MIGRATION_USER`, `AMRS_MIGRATION_PASSWORD` and `AMRS_MIGRATION_DSN` securely in the administrator process environment.
2. Run `python -m amrs.migrate up`. It applies the ordered scripts in `db/schema/` and records SHA-256 checksums, state and the last completed statement in `schema_migrations`. Re-running with the same successful versions makes no changes.
3. Run `python -m amrs.bootstrap`. The interactive wizard requests the administrator's name, login email, initial department and a password with confirmation. It refuses to create a second first administrator. Nothing prints or stores the plaintext password.
4. As the schema owner, call `grant_runtime` for the separate runtime account. The function validates the account identifier. DBA account creation and grants are operator tasks, not normal application actions.
5. Configure `AMRS_DB_USERNAME` to the runtime user, `AMRS_DB_SCHEMA` to the schema owner, and `AMRS_ORACLE_DSN` to the test/production service as appropriate. Set the runtime password through the approved secret mechanism. The pool sets CURRENT_SCHEMA on its own sessions; it does not grant cross-schema privileges by itself.

The two historical migration scripts remain wrappers for `up` and now require the dedicated migration environment. Normal login/attendance/recovery does not create tables or indexes. Missing or mismatched migration state produces an administrator-setup error.

Migration 004 adds camera configuration, append-only runtime audit privileges, biometric-consent records and configurable attendance settings. Migration 005 adds academic classes/sections and an optional class link on existing courses. Neither migration removes application rows or assigns a guessed class to an old course. Existing migration files 001–003 remain unchanged.

## Explicit legacy-schema adoption

Adoption is an administrator maintenance operation. It is never attempted at login or automatically against the Downloads installation. An operator must have explicit owner approval and a backup whose isolated restore has been verified before using `adopt`. This utility cannot prove the semantic correctness of a DBA's restore report; it verifies the artifact bytes and the operator's signed-off assertions. A synthetic approval fixture in a test is not a real backup/restore rehearsal.

1. Stop application writes and schedule a maintenance window. Make a complete backup using the institution's Oracle backup procedure. Restore it into isolation and verify row totals, representative attendance, indexes, constraints, grants and application workflows. Keep the backup and a nonempty restore-verification report outside source control. Manually verify the ADMIN/TEACHER/STUDENT role seed rows; adoption intentionally does not query application rows.
2. A DBA provisions a separate empty, disposable **reference owner** on the same Oracle version and compatible NLS settings, with the migration-owner privileges above. Using its migration environment, run `python -m amrs.migrate up --through 002` (substitute the exact known legacy prefix). Do not copy a production schema into the reference or manually change its objects. A reference history must contain exactly the selected ordered source prefix and checksums.
3. Set `AMRS_MIGRATION_USER/PASSWORD/DSN` securely for the **legacy owner** and `AMRS_REFERENCE_USER/PASSWORD/DSN` for the **reference owner**. Neither is the runtime account. Passwords belong only in secure process configuration, never CLI arguments or a checked-in file.
4. Run `python -m amrs.migrate adopt-plan --through 002 --plan artifacts/adoption-plan.json`. Ensure the parent output folder exists first. This reads owner dictionary metadata only and writes a redacted plan; an existing output plan is not overwritten. Review the target database/container/schema, migration source checksums, fingerprints and differences. An incompatible result is a refusal, not a list of automatic repair statements.
5. A responsible approver prepares a local approval JSON with `plan_sha256` (the printed plan digest), `approved: true`, `restore_verified: true`, `role_seeds_verified: true`, `approved_by` and a timezone-aware `approved_at` timestamp less than 24 hours old. Include absolute `backup_file` and `restore_report_file` paths, plus their independently verified `backup_sha256` and `restore_report_sha256`. No passwords or data contents belong in the plan or approval. Keep these files out of Git.
6. After explicit approval, run `python -m amrs.migrate adopt --plan artifacts/adoption-plan.json --approval artifacts/adoption-approval.json`. A schema-specific DBMS_LOCK excludes another cooperating migrator; a fresh comparison occurs under the lock and again after validating the backup files. The command adds only schema_migrations and records the validated baseline prefix. It does not delete, select or rewrite application records or run the remaining migrations.
7. Run `python -m amrs.migrate up` to apply subsequent versions, then refresh the runtime object's grants. Verify the restored rehearsal again before approving the same steps on a working production schema. Baseline adoption of a working installation has not been executed by this development task.

The comparison covers visible table columns/types/lengths/precision/scale/nullability/defaults, identity generation/options, PK/unique/check/FK constraints and their validation/defer/delete state, index columns/expressions/status/visibility, trigger definitions/status, view definitions, explicit sequences and invalid/unexpected objects. Generated identity sequence and anonymous constraint/index names are normalized; data counters are not compared. Formatting outside SQL literals is normalized while literal and quoted-identifier case are preserved. Schema-qualified self-references are compared independently of owner names. Oracle documents these owner-accessible dictionary views in its [identity-column reference](https://docs.oracle.com/en/database/oracle/oracle-database/26/refrn/ALL_TAB_IDENTITY_COLS.html) and [index-expression reference](https://docs.oracle.com/en/database/oracle/oracle-database/12.2/refrn/ALL_IND_EXPRESSIONS.html).

Unsupported external-schema foreign keys, extra/missing objects, altered definitions, invalid objects, an existing partial registry or a changed approval binding are refused. A divergent historical schema needs an individually reviewed forward compatibility migration and a new restore rehearsal. Adoption does not guess mappings, remove objects, bypass checks or repair arbitrary schema variants. If a process stops after registry DDL but before its rows commit, the empty/incomplete registry requires manual maintenance review; no destructive recovery is automatic.

## Forward migrations and failures

Never edit an applied migration. Add a new numbered script. A changed or unknown historical checksum is refused before subsequent application statements run. Only one migrator for a schema may hold the DBMS_LOCK advisory lock, which persists across Oracle's implicit DDL commits.

DDL is not transactionally reversible in Oracle. The runner checkpoints each successfully executed statement. A failed SQL statement rolls back its DML and leaves the migration incomplete. The operator can correct the external cause and retry the same checksum. If a process dies after DDL commits but before its checkpoint commits, an administrator must inspect that exact object and checkpoint before recovery. The runner does not silently ignore ORA-00955, delete objects or rewrite history.

Back up before upgrading an installation, retain the exact application/migration source, and perform a restore rehearsal in isolation. Recovery is a reviewed forward repair or tested restore, not an automatic destructive `down` command. Never purge the working schema to make a migration pass.

## Native isolated verification on this computer

The owner explicitly selected native Oracle verification and prohibited WSL installation or Windows component changes on 2 November 2026. Native Oracle services were available, and SQLPlus `/ as sysdba` operating-system authentication succeeded without reading a stored password. Native disposable schemas are an alternative verification environment, not evidence of a Docker/container installation test.

From an authorized development shell, run `python -m tools.native_oracle_check` with `AMRS_ALLOW_NATIVE_ISOLATED_TEST=1`. `AMRS_TEST_SQLPLUS` may point to the installed SQLPlus executable. The utility creates random test-only owner/runtime names and passwords in memory in FREEPDB1. It accesses only those schemas, never loads the working `.bat`, tests DDL denial for the runtime user, and removes only users it created in that invocation. It checks schema creation, repeated migration, checksum rejection, row preservation, first-admin refusal on repeat, and interrupted-migration recovery. Mail tests use non-delivering test transports.

The operating-system-authenticated administrative connection is for isolated verification only. It is not a deployment authentication design or a substitute for the target server/credential-manager architecture.

Install development dependencies from `requirements-dev.txt` into a separate development virtual environment before running the utility. It runs the collected pytest suite with Oracle enabled, then ten allowlisted historical scenarios in isolated subprocesses. QR test HTTP servers bind only to loopback. The subprocess adapter redirects historical hard-coded AMRS connections to that invocation's disposable runtime user; it refuses other connection targets. Temporary settings and an empty home/biometric directory prevent these scenarios from reaching working private files. Six historical scripts that depend on private biometric fixtures remain unrun and are named in the report.

Sanitized results are written to ignored `artifacts/native-pytest.xml`, `artifacts/legacy-results.json` and `artifacts/native-summary.json`. Child logs and exception values are not copied to reports because they can contain temporary credentials or QR tokens. A failed pytest suite or legacy scenario produces a nonzero overall result after cleanup and the other checks. Missing fixtures and container deployment are reported separately from passing cases.

## Outstanding acceptance gates

- Working legacy installation: adoption tooling and synthetic fixtures exist, but no production backup approval, restore rehearsal or production adoption has been performed. No protected working data has been imported or modified by this work. A real divergent legacy schema remains subject to a reviewed compatibility migration rather than automatic adoption.
- Container deployment verification is deferred by the owner's native-only instruction. No existing collected test requires Docker. A native pass must not be described as a container deployment pass. Do not install WSL or modify Windows components for this work.
- Convert the historical standalone integration scripts to isolated pytest fixtures in P0-06 before enabling their CI collection.

Do not roll this new source checkout over the running legacy installation until the legacy adoption and remaining Phase 0 gates pass.
