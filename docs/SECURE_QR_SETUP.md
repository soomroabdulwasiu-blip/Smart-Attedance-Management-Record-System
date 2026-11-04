# Secure QR attendance

QR check-in uses the student's AMRS account and enrolled face. The teacher's computer verifies the camera frames against the local face template. Oracle saves attendance only after the student taps **Mark attendance** and the server checks the short-lived verification again.

## One-time HTTPS setup

Phone browsers expose the camera only in a secure context. A plain HTTP URL on the same Wi-Fi cannot run this check-in. The phone must trust the certificate and the QR address must match it. [W3C camera API](https://www.w3.org/TR/mediacapture-streams/#dom-mediadevices-getusermedia)

1. In the Teacher dashboard, go to **QR Attendance → HTTPS setup**.
2. For campus use, enter the hostname or address on the certificate. Choose the campus certificate chain and matching private key in PEM format, then select **Save HTTPS settings**. The hostname must resolve to the teacher computer from the phones and the teacher computer. The campus IT team should configure the certificate and Wi-Fi access.
3. For a small local test without a campus certificate, select **Create reusable classroom certificate**. The app detects the current private Wi-Fi address. Export only `AMRS-QR-Trust.cer`. Compare the SHA-256 fingerprint with the one displayed on the teacher computer before trusting it. Save the HTTPS settings. This replaces the older certificate that was limited to one IP.
4. For the local option, each authorized test phone must install and trust that public certificate. On iPhone or iPad, manually installed roots also need SSL trust enabled under **Settings → General → About → Certificate Trust Settings**. On Android, find certificate installation in **Security & privacy → Encryption & credentials** and use the **CA certificate** option when available. Device menus and managed-phone policy can vary. [Apple trust settings](https://support.apple.com/en-gb/102390) · [Android certificate settings](https://support.google.com/pixelphone/answer/2844832)

Only the public `.cer` file is for phones. The teacher computer keeps the server key and a Windows-encrypted issuing key. The signing chain limits issuance to private LAN IPs and expires after 30 days. During that period, generating a new QR after a Wi-Fi IP change renews the server certificate under the same phone trust entry. At expiry, create a new classroom profile and remove the old phone trust entry. AMRS does not install trust entries. Use a campus certificate for a wider rollout.

## Check in from the phone

1. On the teacher computer, enroll each student in the course and enroll their face with consent using the same Windows profile that will host QR attendance.
2. Choose the course and date on **Mark Attendance**. Open **QR Attendance** and select **Generate QR session**. The app tries the preferred port first and chooses a free port if needed. The generated QR includes the actual address and port. The session lasts 15 minutes.
3. Connect the phone to the same Wi-Fi. Scan the new QR and open the link in the phone browser. Enter the student's roll number and enrollment password, then tap **Verify face**.
4. Allow the front camera. Look straight, then turn slightly when prompted. Keep one face in view. A red box shows an identity mismatch. A green box confirms the server has verified the enrolled face.
5. Tap **Mark attendance** within the verification window and wait for **Attendance confirmed**. The live camera stops as soon as verification completes.

Face matching and the movement prompt deter password sharing and basic static-photo reuse. They are not certified liveness detection and cannot guarantee protection against replayed video or virtual-camera attacks. The app does not save check-in frames. If a student declines face verification or their camera is unavailable, the teacher can review and mark attendance manually.

## Troubleshooting

- **Page unreachable** — Scan the most recent QR. Check that the desktop app is running and that the Wi-Fi permits phones to reach the teacher computer on the displayed port. Campus client isolation or a firewall may require help from IT.
- **Certificate warning** — Check certificate trust and the exact hostname/IP. Do not enter the student's password on an untrusted page.
- **Camera permission denied** — Allow camera access in the phone's browser settings and try again.
- **Face unavailable** — Verify that the student has an active course enrollment and a usable face template in the teacher computer's Windows profile.
- **Already recorded** — A repeat check-in preserves the existing valid attendance. Ask the teacher to review an existing absence.
