"""Run explicitly with AMRS_TEST_ORACLE=1. Uses temporary accounts and fake email delivery."""
import os
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from amrs import db, recovery, mail_delivery

pytestmark = pytest.mark.skipif(os.getenv('AMRS_TEST_ORACLE') != '1', reason='Requires local Oracle integration environment')
OLD = 'Original-test-password-123'
NEW = 'Changed-test-password-456'


@pytest.fixture(params=['STUDENT', 'TEACHER'])
def account(request, monkeypatch):
    recovery.ensure_schema()
    role = request.param
    tag = uuid.uuid4().hex[:12]
    email = f'recovery-{tag}@example.test'
    if role == 'STUDENT':
        dept = db.departments()[0]['dept_id']
        db.signup_student('Recovery integration', email, OLD, 'R' + tag.upper(), dept, 1, 2026)
    else:
        db.signup_teacher('Recovery integration', email, OLD, 'Testing')
    user = db.login(role, email, OLD)
    mailbox = []
    monkeypatch.setattr(mail_delivery, 'load_settings', lambda: ('test@example.test', 'not-a-real-secret'))
    monkeypatch.setattr(mail_delivery, 'send_mail', lambda *args: mailbox.append(args))
    try:
        yield role, email, user, mailbox
    finally:
        with db.connection() as c:
            c.cursor().execute('DELETE FROM email_password_resets WHERE user_id=:id AND user_type=:role', {'id': user['user_id'], 'role': role})
        if role == 'STUDENT': db.delete_student_permanently(user['user_id'])
        else: db.delete_teacher_permanently(user['user_id'])


def issue(account):
    role, email, _, mailbox = account
    token = recovery.request_code(role, email)
    assert mailbox[-1][0] == email
    code = re.search(r'code is: (\d{6})', mailbox[-1][2]).group(1)
    return token, code


def test_success_old_password_rejected_replay_denied(account):
    role, email, user, mailbox = account
    token, code = issue(account)
    row = db.one('SELECT code_hash FROM email_password_resets WHERE request_id=:id', {'id': token})
    assert row['code_hash'] != code and row['code_hash'].startswith('$2')
    assert recovery.complete_reset(role, token, code, NEW)
    assert db.login(role, email, NEW)['user_id'] == user['user_id']
    with pytest.raises(ValueError): db.login(role, email, OLD)
    with pytest.raises(ValueError): recovery.complete_reset(role, token, code, 'Another-password-789')
    assert len(mailbox) == 2 and 'successful' in mailbox[-1][1]
    assert NEW not in mailbox[-1][2]


def test_wrong_code_commits_attempts_and_locks(account):
    role = account[0]
    token, code = issue(account)
    wrong = '999999' if code != '999999' else '000000'
    for _ in range(5):
        with pytest.raises(ValueError): recovery.complete_reset(role, token, wrong, NEW)
    row = db.one('SELECT attempts,status FROM email_password_resets WHERE request_id=:id', {'id': token})
    assert row['attempts'] == 5 and row['status'] == 'LOCKED'
    with pytest.raises(ValueError): recovery.complete_reset(role, token, code, NEW)
    assert db.login(role, account[1], OLD)


def test_expiry_role_scope_and_changed_password(account):
    role, email, user, _ = account
    token, code = issue(account)
    other = 'TEACHER' if role == 'STUDENT' else 'STUDENT'
    with pytest.raises(ValueError): recovery.complete_reset(other, token, code, NEW)
    with db.connection() as c:
        c.cursor().execute("UPDATE email_password_resets SET expires_at=SYS_EXTRACT_UTC(SYSTIMESTAMP)-INTERVAL '1' MINUTE WHERE request_id=:id", {'id': token})
    with pytest.raises(ValueError): recovery.complete_reset(role, token, code, NEW)
    with db.connection() as c:
        c.cursor().execute("UPDATE email_password_resets SET expires_at=SYS_EXTRACT_UTC(SYSTIMESTAMP)+INTERVAL '10' MINUTE WHERE request_id=:id", {'id': token})
    db.change_password(user, OLD, NEW)
    with pytest.raises(ValueError): recovery.complete_reset(role, token, code, 'Third-password-789')


def test_smtp_failure_preserves_password(account, monkeypatch):
    def fail(*args): raise ValueError('Simulated SMTP failure')
    monkeypatch.setattr(mail_delivery, 'send_mail', fail)
    with pytest.raises(ValueError): recovery.request_code(account[0], account[1])
    assert db.login(account[0], account[1], OLD)
    row = db.one('SELECT status FROM email_password_resets WHERE user_id=:id', {'id': account[2]['user_id']})
    assert row['status'] == 'FAILED'


def test_notification_failure_does_not_undo_password(account, monkeypatch):
    token, code = issue(account)
    def fail(*args): raise ValueError('Simulated SMTP failure')
    monkeypatch.setattr(mail_delivery, 'send_mail', fail)
    assert recovery.complete_reset(account[0], token, code, NEW) is False
    assert db.login(account[0], account[1], NEW)
    assert db.one('SELECT notification FROM email_password_resets WHERE request_id=:id', {'id': token})['notification'] == 'FAILED'


def test_cooldown_hour_limit_and_new_code_invalidates_old(account):
    role, email, user, mailbox = account
    first, first_code = issue(account)
    recovery.request_code(role, email)
    assert len(mailbox) == 1
    for _ in range(4):
        with db.connection() as c:
            c.cursor().execute("UPDATE email_password_resets SET created_at=SYS_EXTRACT_UTC(SYSTIMESTAMP)-INTERVAL '2' MINUTE WHERE user_id=:id", {'id': user['user_id']})
        issue(account)
    assert len(mailbox) == 5
    with pytest.raises(ValueError): recovery.complete_reset(role, first, first_code, NEW)
    with db.connection() as c:
        c.cursor().execute("UPDATE email_password_resets SET created_at=SYS_EXTRACT_UTC(SYSTIMESTAMP)-INTERVAL '2' MINUTE WHERE user_id=:id", {'id': user['user_id']})
    recovery.request_code(role, email)
    assert len(mailbox) == 5


def test_concurrent_redemption_only_once(account):
    token, code = issue(account)
    def redeem():
        try: return recovery.complete_reset(account[0], token, code, NEW)
        except ValueError: return 'rejected'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: redeem(), range(2)))
    assert results.count(True) == 1 and results.count('rejected') == 1


def test_unknown_and_inactive_not_delivered(account):
    role, email, user, mailbox = account
    recovery.request_code(role, uuid.uuid4().hex + '@example.test')
    assert mailbox == []
    token, code = issue(account)
    table, col = ('students', 'student_id') if role == 'STUDENT' else ('users', 'user_id')
    with db.connection() as c:
        c.cursor().execute(f'UPDATE {table} SET is_active=0 WHERE {col}=:id', {'id': user['user_id']})
    recovery.request_code(role, email)
    assert len(mailbox) == 1
    with pytest.raises(ValueError): recovery.complete_reset(role, token, code, NEW)
