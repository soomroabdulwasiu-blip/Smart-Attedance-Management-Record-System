"""Responsive email recovery and administrator mail setup dialogs."""
import time
from PySide6.QtCore import Qt, QThreadPool, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QFrame, QLayout
from . import recovery, mail_delivery
from .gui import BackgroundTask

STYLE = '''
QWidget { font-family: 'Segoe UI'; font-size: 13px; }
QDialog { background: #101a2d; }
QLabel { color: #bdcce3; font-size: 13px; background: transparent; }
QLabel#title { color: #f3f7ff; font-size: 24px; font-weight: 700; }
QLabel#step { color: #9fb8ff; font-weight: 600; }
QLabel#notice { color: #dbe7ff; background: #1d304d; border-radius: 8px; padding: 12px; }
QFrame#form { background: #16243b; border: 1px solid #354967; border-radius: 12px; }
QLineEdit { color: #f4f7ff; background: #0e1b30; border: 1px solid #496285; border-radius: 8px; padding: 10px; min-height: 20px; }
QLineEdit:focus { border: 1px solid #91aaff; }
QPushButton { background: #4e67df; color: white; border-radius: 8px; padding: 11px 16px; font-weight: 600; }
QPushButton:hover { background: #637cf0; }
QPushButton:disabled { background: #293a5b; color: #91a2bf; }
QPushButton#secondary { background: #283e5c; }
'''


class AsyncDialog(QDialog):
    def __init__(self, parent, title, subtitle):
        super().__init__(parent)
        self._task = None
        self.setWindowTitle(title)
        self.setStyleSheet(STYLE)
        self.setMinimumWidth(520)
        self.resize(560, 440)
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(26, 24, 26, 24)
        self.outer.setSpacing(14)
        heading = QLabel(title); heading.setObjectName('title'); self.outer.addWidget(heading)
        sub = QLabel(subtitle); sub.setWordWrap(True); self.outer.addWidget(sub)
        self.form = QFrame(); self.form.setObjectName('form')
        self.body = QVBoxLayout(self.form); self.body.setContentsMargins(20, 18, 20, 18); self.body.setSpacing(10)
        self.body.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.outer.addWidget(self.form)
        self.notice = QLabel(''); self.notice.setObjectName('notice'); self.notice.setWordWrap(True); self.notice.setTextFormat(Qt.TextFormat.PlainText)
        self.outer.addWidget(self.notice)
        self.controls = QFrame(); self.footer = QHBoxLayout(self.controls); self.footer.setContentsMargins(0, 0, 0, 0)
        self.outer.addWidget(self.controls)

    def entry(self, label, secret=False):
        caption = QLabel(label); caption.setMinimumHeight(22); self.body.addWidget(caption)
        edit = QLineEdit()
        edit.setMinimumHeight(42)
        if secret: edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.body.addWidget(edit)
        return edit, caption

    def task(self, fn, success, message):
        if self._task: return
        self.form.setEnabled(False); self.controls.setEnabled(False); self.notice.setText(message)
        self._success = success
        self._task = BackgroundTask(fn)
        self._task.signals.succeeded.connect(self._done, Qt.ConnectionType.QueuedConnection)
        self._task.signals.failed.connect(self._failed, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(self._task)

    def _finish(self):
        self._task = None; self.form.setEnabled(True); self.controls.setEnabled(True)

    def _done(self, result):
        self._finish(); self._success(result)

    def _failed(self, exc):
        self._finish()
        self.notice.setText(str(exc) if isinstance(exc, ValueError) else 'The request could not be completed. Check the Oracle connection and try again.')

    def reject(self):
        if not self._task: super().reject()

    def closeEvent(self, event):
        if self._task: event.ignore()
        else: super().closeEvent(event)


class PasswordRecoveryDialog(AsyncDialog):
    def __init__(self, parent, role, email=''):
        super().__init__(parent, 'Reset your password',
                         f'{role.title()} account recovery • Verify your registered email to choose a new password.')
        self.role = role; self.token = None; self.sent_email = ''; self.until = 0
        self.step = QLabel('STEP 1 OF 2 · VERIFY YOUR EMAIL'); self.step.setObjectName('step'); self.body.addWidget(self.step)
        self.email, _ = self.entry('Registered account email')
        if '@' in email: self.email.setText(email.strip())
        self.code, self.code_label = self.entry('Six-digit email code'); self.code.setMaxLength(6)
        self.password, self.password_label = self.entry('New password (at least 8 characters)', True)
        self.confirm, self.confirm_label = self.entry('Confirm new password', True)
        self.secret_widgets = [self.code, self.code_label, self.password, self.password_label, self.confirm, self.confirm_label]
        for w in self.secret_widgets: w.hide()
        self.cancel = QPushButton('Cancel'); self.cancel.setObjectName('secondary'); self.cancel.clicked.connect(self.reject)
        self.resend = QPushButton('Resend code'); self.resend.setObjectName('secondary'); self.resend.clicked.connect(self.send); self.resend.hide()
        self.change_email = QPushButton('Change email'); self.change_email.setObjectName('secondary'); self.change_email.clicked.connect(self.start_again); self.change_email.hide()
        self.submit = QPushButton('Send verification code'); self.submit.clicked.connect(self.submit_form)
        for w in (self.cancel, self.change_email, self.resend, self.submit): self.footer.addWidget(w)
        self.notice.setText('Use the email attached to your AMRS login. Your Gmail password is never required.')
        self.timer = QTimer(self); self.timer.setInterval(1000); self.timer.timeout.connect(self.tick)
        self.email.returnPressed.connect(self.submit_form); self.confirm.returnPressed.connect(self.submit_form)

    def submit_form(self):
        if self._task: return
        if not self.token: return self.send()
        if self.password.text() != self.confirm.text():
            self.notice.setText('New passwords do not match.'); return
        code, password, token = self.code.text().strip(), self.password.text(), self.token
        self.task(lambda: recovery.complete_reset(self.role, token, code, password), self.completed, 'Verifying code and resetting your password…')

    def send(self):
        if self._task: return
        if self.token and time.monotonic() < self.until: return
        try: email = mail_delivery.valid_email(self.email.text())
        except ValueError as exc: self.notice.setText(str(exc)); return
        self.sent_email = email
        self.task(lambda: recovery.request_code(self.role, email), self.sent, 'Sending verification email…')

    def sent(self, token):
        self.token = token; self.email.setReadOnly(True)
        self.code.clear(); self.password.clear(); self.confirm.clear()
        for w in self.secret_widgets: w.show()
        self.step.setText('STEP 2 OF 2 · ENTER CODE & NEW PASSWORD')
        self.submit.setText('Reset password'); self.resend.show(); self.change_email.show()
        self.until = time.monotonic() + 60; self.timer.start(); self.tick()
        self.notice.setText(recovery.GENERIC + '\nResend is available after 60 seconds (maximum 5 emails per hour).')
        self.code.setFocus(); self.adjustSize()

    def start_again(self):
        if self._task: return
        self.timer.stop(); self.token = None; self.until = 0
        self.code.clear(); self.password.clear(); self.confirm.clear()
        for w in self.secret_widgets: w.hide()
        self.email.setReadOnly(False); self.email.setFocus(); self.email.selectAll()
        self.resend.hide(); self.change_email.hide()
        self.step.setText('STEP 1 OF 2 · VERIFY YOUR EMAIL')
        self.submit.setText('Send verification code')
        self.notice.setText('Enter the email registered to your AMRS login. Existing email request limits still apply.')
        self.adjustSize()

    def tick(self):
        seconds = max(0, int(self.until - time.monotonic()) + 1)
        self.resend.setEnabled(seconds == 0)
        self.resend.setText(f'Resend in {seconds}s' if seconds else 'Resend code')
        if not seconds: self.timer.stop()

    def completed(self, notified):
        self.timer.stop(); self.password.clear(); self.confirm.clear(); self.code.clear(); self.token = None
        self.form.hide(); self.resend.hide(); self.change_email.hide(); self.submit.hide()
        self.cancel.setText('Back to sign in')
        self.notice.setText('Password reset successfully. You can now sign in with your new password.\n' +
                           ('A confirmation email has been sent.' if notified else
                            'The password was saved, but the confirmation email could not be sent. Contact your administrator if needed.'))


class GmailSettingsDialog(AsyncDialog):
    def __init__(self, parent, user):
        if user.get('role') != 'ADMIN': raise ValueError('Administrator access required.')
        super().__init__(parent, 'Gmail delivery settings',
                         'Administrator setup — students and teachers will receive reset codes at their own registered email addresses.')
        defaults = mail_delivery.setup_defaults()
        self.sender, _ = self.entry('1. Sender Gmail — AMRS sends emails from this account')
        self.sender.setText(mail_delivery.configured_sender() or defaults['sender'])
        links = QHBoxLayout()
        self.security_link = QPushButton('Enable 2-Step Verification'); self.security_link.setObjectName('secondary')
        self.password_link = QPushButton('Create Google App Password'); self.password_link.setObjectName('secondary')
        self.security_link.setMinimumHeight(42); self.password_link.setMinimumHeight(42)
        self.setMinimumWidth(620)
        self.setMinimumHeight(680)
        self.security_link.clicked.connect(lambda: self.open_google('https://myaccount.google.com/signinoptions/two-step-verification'))
        self.password_link.clicked.connect(lambda: self.open_google('https://myaccount.google.com/apppasswords'))
        links.addWidget(self.security_link); links.addWidget(self.password_link); self.body.addLayout(links)
        self.secret, _ = self.entry('2. Paste the 16-letter App Password Google creates for AMRS', True)
        self.recipient, _ = self.entry('3. Test inbox — check this Gmail after saving')
        self.recipient.setText(defaults['recipient'])
        self.notice.setText('In Google, sign in with the sender account shown above. Enable 2-Step Verification, open App Passwords, enter AMRS as the app name, then create and paste the password here. Do not use your normal Gmail password.')
        self.close_button = QPushButton('Close'); self.close_button.clicked.connect(self.reject)
        self.save_button = QPushButton('Save & send test'); self.save_button.clicked.connect(self.save)
        self.test_button = QPushButton('Send test email'); self.test_button.clicked.connect(self.test)
        for w in (self.close_button, self.save_button, self.test_button): self.footer.addWidget(w)
        self.adjustSize()

    def save(self):
        try:
            sender = mail_delivery.valid_email(self.sender.text())
            recipient = mail_delivery.valid_email(self.recipient.text())
        except ValueError as exc:
            self.notice.setText(str(exc)); return
        secret = self.secret.text()
        if not secret and sender != mail_delivery.configured_sender():
            self.notice.setText('First create the Google App Password using the button above, then paste it into step 2.'); return
        def configure():
            if secret: mail_delivery.save_settings(sender, secret)
            try: mail_delivery.send_test(recipient)
            except ValueError as exc: raise ValueError('Sender settings are saved, but the test email failed. '+str(exc)) from None
        self.task(configure, self.saved, 'Verifying sender settings and sending a real test email…')

    def saved(self, _):
        self.secret.clear(); self.notice.setText('Sender settings saved. Gmail accepted the test email. Check the test Inbox and Spam. Teacher and Student password recovery can now send verification codes.')

    def open_google(self, url):
        if not QDesktopServices.openUrl(QUrl(url)):
            self.notice.setText('Open this address in your browser: '+url)

    def test(self):
        try: recipient = mail_delivery.valid_email(self.recipient.text())
        except ValueError as exc: self.notice.setText(str(exc)); return
        if self.sender.text().strip().lower() != mail_delivery.configured_sender() or self.secret.text():
            self.notice.setText('Verify & save these settings before sending a test.'); return
        self.task(lambda: mail_delivery.send_test(recipient),
                  lambda _: self.notice.setText('Gmail accepted the test email. Check the recipient Inbox and Spam folder.'), 'Sending test email…')
