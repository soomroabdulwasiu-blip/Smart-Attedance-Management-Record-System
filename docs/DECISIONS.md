# Approved direction and configurable starting policies

The owner approved client/server architecture with server-side face matching and delegated other routine choices on 2 November 2026. These decisions guide later work; P0-01 does not implement new authentication or attendance rules.

- Keep Python, PySide6 and Oracle mandatory. Target Windows 10/11 x64 first. Do not advertise Linux/macOS support until tested.
- Start with local Git. No remote repository, public hosting, published CI run or customer deployment has been authorized or created.
- Use a disposable, test-only Oracle Free instance for database verification when provisioned. Never use production credentials or real face files in automated tests. Database edition for commercial operation remains an institutional licensing decision, not a guessed purchase.
- On 2 November 2026 the owner explicitly selected native Oracle testing instead of Docker verification and prohibited installing WSL or changing Windows components. Run synthetic fixtures in newly created disposable schemas on the existing native service; remove only accounts created by that invocation. Container deployment verification is deferred by this decision, not claimed as passing.
- English is the initial interface. Build translation boundaries for English/Urdu later; do not claim an Urdu release now.
- Maintain a local pilot adapter during migration. The target deployment keeps Oracle and biometric templates on the server, with camera capture/detection on the client and matching on the server.
- Proposed configurable attendance starting settings: minimum 75%; late after 10 minutes; absent after 30 minutes; LATE counts toward attendance; teacher editing window 3 days. Approved leave is excluded from the denominator. These values must be reviewed in the institute setup wizard and applied prospectively, not retroactively to current records.
- Leave decisions go to the assigned teacher, with HOD/admin escalation. Do not invent an institutional approver's identity.
- Separate recoverable deactivation from explicit permanent deletion. Retain the owner's requested permanent-delete option and identifier reuse. Require dependency preview and confirmation; no new delete or deactivation policy is applied by this package.
- Propose 12-character passwords and 5-failure progressive lockout for P1, with administrator TOTP in the server deployment. Existing user passwords are not changed by P0-01.
- Email is the initial notification channel. Support institutional SMTP later. SMS/WhatsApp and guardian contact collection remain disabled unless selected in institution setup.
- Prefer trusted HTTPS for QR; leave geolocation disabled. Campus subnet and proxy-attendance restrictions require the actual deployment network, not a guessed CIDR.
- Do not invent retention periods for the institute. Keep cleanup automation off until the setup wizard records attendance, audit, biometric and attachment retention. Until then, do not silently delete or migrate existing data.
- P0 maintenance logs will record redacted maintenance actions. The append-only database audit design belongs to P1 and must be integrated before a production purge is enabled.
- Code-signing certificate, final licensing, legal/consent wording, pilot cohort and target load budgets need real deployment information. Do not claim commercial readiness before those checks.

