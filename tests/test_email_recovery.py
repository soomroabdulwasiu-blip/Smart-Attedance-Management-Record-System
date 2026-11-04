import os
import time
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEventLoop, QTimer
from amrs import mail_delivery, recovery
from amrs.recovery_ui import PasswordRecoveryDialog, GmailSettingsDialog


def test_mail_encrypted_at_rest_and_authenticated(tmp_path, monkeypatch):
    monkeypatch.setattr(mail_delivery, 'CONFIG_PATH', tmp_path / 'gmail.json')
    calls = []
    class Client:
        def close(self): calls.append('closed')
    monkeypatch.setattr(mail_delivery, '_smtp', lambda sender, secret: Client())
    secret = 'abcdefghijklmnop'
    mail_delivery.save_settings('sender@gmail.com', secret)
    assert calls == ['closed']
    assert secret not in mail_delivery.CONFIG_PATH.read_text()
    assert mail_delivery.load_settings() == ('sender@gmail.com', secret)


def test_smtp_uses_verified_tls_and_never_emails_password(monkeypatch):
    calls = []
    monkeypatch.setattr(mail_delivery, 'load_settings', lambda: ('sender@gmail.com', 'app-secret'))
    class Client:
        def __init__(self, host, port, context, timeout):
            assert host == 'smtp.gmail.com' and port == 465 and context.check_hostname and timeout == 15
        def login(self, user, password): calls.append('authenticated')
        def send_message(self, msg):
            assert msg['To'] == 'recipient@gmail.com'
            assert 'app-secret' not in msg.as_string()
            calls.append('sent'); return {}
        def close(self): pass
    monkeypatch.setattr(mail_delivery.smtplib, 'SMTP_SSL', Client)
    mail_delivery.send_test('recipient@gmail.com')
    assert calls == ['authenticated', 'sent']


@pytest.mark.parametrize('email', ['invalid', 'x@y\nBcc:z@y.com', 'x@y.com\r\nOther:value', 'a@b'])
def test_invalid_email(email):
    with pytest.raises(ValueError): mail_delivery.valid_email(email)


def test_admin_recovery_and_nonadmin_configuration_rejected():
    with pytest.raises(ValueError): recovery.request_code('ADMIN', 'admin@gmail.com')
    with pytest.raises(ValueError): GmailSettingsDialog(None, {'role': 'STUDENT'})


def events(ms):
    loop = QEventLoop(); QTimer.singleShot(ms, loop.quit); loop.exec()


def test_two_stage_form_is_responsive_and_clears_secrets(monkeypatch):
    app = QApplication.instance() or QApplication([])
    calls = []
    def slow_send(role, email):
        time.sleep(.25); calls.append((role, email)); return 'test-token'
    monkeypatch.setattr(recovery, 'request_code', slow_send)
    monkeypatch.setattr(recovery, 'complete_reset', lambda *a: True)
    d = PasswordRecoveryDialog(None, 'STUDENT'); d.show()
    assert not d.password.isVisible()
    d.email.setText('student@gmail.com'); d.submit_form()
    heartbeat = []; QTimer.singleShot(30, lambda: heartbeat.append(True))
    d.reject(); assert d.isVisible()  # Do not destroy a live worker.
    events(500)
    assert heartbeat and calls == [('STUDENT', 'student@gmail.com')]
    assert d.password.isVisible() and d.email.isReadOnly() and not d.resend.isEnabled()
    d.password.setText('New-password-123'); d.confirm.setText('different'); d.submit_form()
    assert 'do not match' in d.notice.text()
    d.code.setText('123456'); d.confirm.setText('New-password-123'); d.submit_form(); events(250)
    assert 'Password reset successfully' in d.notice.text()
    assert not d.password.text() and not d.confirm.text() and not d.code.text()
    d.close()


def test_mail_error_keeps_form_retryable(monkeypatch):
    app = QApplication.instance() or QApplication([])
    def fail(*args): raise ValueError('Gmail could not accept the email.')
    monkeypatch.setattr(recovery, 'request_code', fail)
    d = PasswordRecoveryDialog(None, 'TEACHER'); d.email.setText('teacher@gmail.com'); d.send(); events(250)
    assert not d.token and d.controls.isEnabled() and 'could not accept' in d.notice.text()
    d.close()


def test_guided_setup_validates_before_sending_and_sends_after_save(monkeypatch):
    monkeypatch.setattr(mail_delivery, 'configured_sender', lambda: '')
    monkeypatch.setattr(mail_delivery, 'setup_defaults', lambda: {'sender':'sender@gmail.com','recipient':'inbox@gmail.com'})
    calls=[]
    monkeypatch.setattr(mail_delivery, 'save_settings', lambda *a: calls.append(('save',a[0])))
    monkeypatch.setattr(mail_delivery, 'send_test', lambda recipient: calls.append(('send',recipient)))
    d=GmailSettingsDialog(None, {'role':'ADMIN'})
    d.save()
    assert not calls and 'First create' in d.notice.text()
    d.secret.setText('abcdefghijklmnop');d.save();events(250)
    assert calls == [('save','sender@gmail.com'),('send','inbox@gmail.com')]
    assert not d.secret.text() and 'Gmail accepted' in d.notice.text()
    d.close()


def test_changing_recovery_email_discards_sensitive_form_state():
    d=PasswordRecoveryDialog(None,'STUDENT','first@gmail.com')
    assert d.email.text()=='first@gmail.com'
    d.sent('old-token');d.code.setText('123456');d.password.setText('Some-password')
    d.start_again()
    assert d.token is None and not d.email.isReadOnly()
    assert not d.code.text() and not d.password.text()
    assert not d.timer.isActive() and d.change_email.isHidden()
    d.close()
