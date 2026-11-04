# Workflow authorization and attendance integrity

The existing desktop repositories remain in place. These safeguards apply to the development checkout with migrations 004 and later, rather than modifying the installed Downloads application or working database.

## Principals and active accounts

`require_actor(user, roles)` checks a principal's shape and allowed role before a query is issued. Unknown roles can no longer fall through to unrestricted attendance or course lists. `session_is_active(user)` verifies the current Oracle account state and its role. A principal dictionary is an in-process desktop value, not a signed network session; it must not become a future server's authentication boundary.

Attendance writes verify active teacher role, current course assignment, course state, student state and enrollment in their authorization query. Sensitive administrator actions that supply `actor=` verify the active administrator in the same transaction. Teacher/student summaries accept an actor to prevent viewing another person's summary; the GUI should always supply its signed-in user. The legacy identifier-only helper signatures remain internal compatibility APIs for fixture setup and existing code, not endpoints to expose over a network.

`authorized_course_students(user, course_id)` is the scoped roster entry point for new presentation code. Students cannot fetch classmates' roster data through it. `student_profile(user)` exposes only the active student's own profile. `audit_records(user)` requires an active administrator and bounds the result count.

## Automated check-ins and manual decisions

The data-access boundary rejects unknown attendance methods, automated ABSENT requests, invalid dates, nonfinite face scores and scores below the configured confidence threshold. A face score must be within the supported similarity range; QR/manual requests cannot attach a face score.

Automated FACE and QR check-ins insert a missing daily record but preserve an existing record and its method. An existing PRESENT or LATE returns `False` from `mark_attendance`, meaning already recorded; it does not produce another audit event. An existing absence or conflicting correction raises an actionable manual-review error. Manual changes remain explicit writes and retain the existing optimistic snapshot checks. The unique course/student/date constraint and duplicate-race recovery remain in force.

Teacher corrections lock the authorized attendance row, require a reason and enforce the configured editing window. Manual single-record and bulk updates also refuse changes to existing expired records, so the correction form cannot be bypassed through the roster. Student correction requests are limited to the student's own records. Approval locks the request and attendance row together and checks the same editing window; rejection remains possible after the window closes. Initial historical manual entry is not blocked by the correction window. A historical insertion that loses a unique-key race rechecks this rule before updating the winner's row.

## Attendance policy and reports

`ATTENDANCE_POLICY` is read from Oracle `attendance_settings.value_json`. Defaults are minimum 75%, a three-day correction window and LATE counting as present. Malformed stored policy causes an administrator-review error rather than silently changing calculations. Course and student summaries apply the current late-counting setting, expose the configured minimum and whether the student's recorded percentage meets it. Course summaries and attendance history accept validated inclusive date filters with bound SQL parameters. Changing policy affects current report calculations; it does not rewrite attendance rows.

## Audit transactions and read preload

Attendance, manual changes, corrections, approvals, password changes and administrator actions append events to `app_audit` in their own data transaction. Audit write failure therefore rolls back the associated action. Events contain identifiers, action names and status transitions; plaintext passwords, biometric images, reset codes and free-form correction reasons are not copied into the audit log. Actual correction reasons remain on the authorized attendance/request records. Runtime permissions permit audit SELECT/INSERT, with no UPDATE/DELETE grant. A schema owner or privileged DBA can still modify these tables; this is not a cryptographically tamper-proof audit system.

`capture_reads()` collects deep-copied query results during background presentation preloading. `use_reads(snapshot)` lets initial page construction consume only those in-memory results. A missing query raises `ReadSnapshotMiss`; it never falls back to foreground Oracle I/O. Contexts are thread-local and restored when their scope exits. Snapshots are not serialized to disk and are not an authorization cache for later user actions.

## Validation and limits

New tests cover rejected roles and scores, cross-account reads, date ranges, correction-window rules, snapshot isolation, audit rollback and duplicate behavior. Guarded native Oracle cases cover persisted duplicate preservation, policy-sensitive percentages, date-scoped reports, approvals, audit write permissions and refused corrections. These cases refuse a target that is not the native test utility's generated disposable owner/runtime pair.

Full signed server sessions, production lockout policy, institutional retention decisions and physically validated face/liveness performance remain separate deployment work. Passing automated tests does not establish those properties.
