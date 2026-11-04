# Administrator, teacher and student workflows

## Administrator

Sign in with the account created by the bootstrap wizard. Students, teachers, courses and enrollment retain their existing management pages. Account operations now pass the acting administrator to backend authorization/audit checks. Teacher self-registration stays pending until approval. Student self-registration creates a new account; an existing student cannot be claimed using only a roll number.

**Classes & sections** groups courses by department, semester, section and academic year. Select a saved class and link a course with matching department/semester. Linking does not silently enroll students. Use the existing course-enrollment controls. Removing a grouping preserves courses and attendance.

**Hardware & cameras** saves enabled sources in Oracle. Add a device, review its connection details and timeouts, test/preview it, save it, then select it for attendance. Local discovery is an explicit scan of compatible camera indices, not an automatic startup action. Manufacturer names are not invented. Simulated sources are clearly labelled and contain generated shapes rather than student photographs. Stop a preview before switching/removing its source. Last status is the last observation, not proof of current availability.

Before enrolling a face, read the consent notice to the student and obtain voluntary agreement. The administrator attests to this explicitly. Batch enrollment requires individual photos and consent for every listed student. New enrollment stores an encrypted face representation, not the submitted photograph. **Withdraw face consent** disables matching and removes local reference files; manual attendance remains available. Institutional retention/consent governance and a backup policy must still be approved for a pilot.

**Settings, audit & diagnostics** controls minimum percentage, the teacher correction window and whether late counts toward percentage. It displays recent authorized Oracle audit events, checks schema/model availability and exports redacted logs plus dependency versions. Passwords, camera secrets, templates and database records are excluded from that diagnostics ZIP.

Permanent student/teacher/course deletion has an explicit destructive confirmation. Related history may be removed as the confirmation states. This is different from withdrawing biometric consent or disabling a camera. Do not use production deletion as a test.

## Teacher

Register, wait for administrator approval, then sign in using your email/password. Only assigned active courses are eligible for attendance. Choose the course/date and load the enrolled roster. Manual submission saves only new/changed statuses and checks the loaded snapshot to prevent overwriting another attendance update unnoticed.

For face attendance, refresh **Saved cameras** and select an enabled source, or use a local laptop-camera index. Start attendance. Recognition validates known faces independently, rejects uncertain/ambiguous matches and shows green only after database success. Amber means verification/saving/retry, red means unknown or uncertain. A saved event displays the student's name/roll and plays a system beep. The enlarged view preserves aspect ratio. A disconnect uses the configured bounded reconnect behavior; pending database saves finish before shutdown.

For QR, select an assigned course/date and generate an HTTPS session. Students sign in, use the phone camera to verify their enrolled face, then tap **Mark attendance**. A short-lived, one-use browser ticket prevents credentials alone from marking attendance. See [Secure QR setup](SECURE_QR_SETUP.md) for certificate and phone instructions.

Repeated FACE/QR check-ins do not overwrite an existing valid present/late record. A conflicting recorded absence requires teacher review. Corrections, including manual edits, respect the configured editing window and are audited. Course reports, date-filtered history and CSV export use authorized Oracle data.

## Student

Create a new account with your email and roll number, then sign in using either identity. View your profile, enrolled courses/class groups, attendance history and percentages. Submit a correction request against one of your own records; the assigned teacher decides. Students cannot directly edit attendance or access camera administration.

Forgot password uses the existing registered-email verification-code workflow. Live Gmail delivery requires an authorized sender and a Google App Password configured by the administrator. Automated tests use non-delivering transports. No real email delivery is claimed until that setup and an authorized inbox test are completed.

## Limits to understand

The local pilot uses one Windows user for encrypted camera credentials and face templates. A future server deployment needs its own server-side secret/biometric custody. No liveness/anti-spoofing protection or reliable 10–20-person classroom accuracy is claimed. Follow HARDWARE_INTEGRATION.md for consenting-participant, lighting, distance, unknown-face and disconnection acceptance tests.
