"""Single-use email recovery backed by Oracle, with bounded guesses and requests."""
import re
import secrets
import threading
import uuid
from . import db, mail_delivery

_ready = False
_lock = threading.Lock()
GENERIC = 'If an active account matches this email, a verification code has been sent. Check Inbox and Spam. Codes expire after 10 minutes.'
INVALID = 'The code is invalid, expired or already used. Request a new code if needed.'
def ensure_schema():
    """Check migration state only. The runtime account must never perform DDL."""
    global _ready
    if _ready:
        return
    with _lock:
        if not _ready:
            from .migrations.runner import require_current
            with db.connection() as connection:
                require_current(connection)
            _ready = True


def _role(role):
    if role not in ('STUDENT', 'TEACHER'):
        raise ValueError('Email recovery is available for students and teachers only.')


def _account(cur, role, email):
    if role == 'STUDENT':
        cur.execute("""SELECT l.student_id,l.email,l.password_hash FROM student_logins l
          JOIN students s ON s.student_id=l.student_id WHERE l.is_active=1 AND s.is_active=1
          AND LOWER(l.email)=:email FOR UPDATE OF l.password_hash,s.is_active""", {'email': email})
    else:
        cur.execute("""SELECT u.user_id,u.email,u.password_hash FROM users u
          JOIN roles r ON r.role_id=u.role_id WHERE u.is_active=1 AND r.role_name='TEACHER'
          AND LOWER(u.email)=:email FOR UPDATE OF u.password_hash""", {'email': email})
    return cur.fetchone()


def request_code(role, email):
    _role(role)
    email = mail_delivery.valid_email(email)
    mail_delivery.load_settings()  # Report missing configuration before account lookup.
    ensure_schema()
    token = str(uuid.uuid4())
    code = f'{secrets.randbelow(1000000):06d}'
    digest = db.hash_password('AMRS-code:' + code)
    deliver = False
    with db.connection() as c:
        cur = c.cursor()
        account = _account(cur, role, email)
        if account:
            params = {'role': role, 'id': account[0]}
            cur.execute("""SELECT COUNT(*),
              SUM(CASE WHEN created_at > SYS_EXTRACT_UTC(SYSTIMESTAMP)-INTERVAL '60' SECOND THEN 1 ELSE 0 END)
              FROM email_password_resets WHERE user_type=:role AND user_id=:id
              AND created_at > SYS_EXTRACT_UTC(SYSTIMESTAMP)-INTERVAL '1' HOUR""", params)
            count, recent = cur.fetchone()
            if count < 5 and not recent:
                cur.execute("""UPDATE email_password_resets SET status='INVALIDATED',code_hash='!'
                  WHERE user_type=:role AND user_id=:id AND status IN ('SENDING','SENT')""", params)
                cur.execute("""INSERT INTO email_password_resets
                  (request_id,user_type,user_id,user_email,code_hash,password_version,expires_at,status)
                  VALUES(:token,:role,:id,:email,:digest,:version,
                  SYS_EXTRACT_UTC(SYSTIMESTAMP)+INTERVAL '10' MINUTE,'SENDING')""",
                  dict(params, token=token, email=account[1], digest=digest, version=account[2]))
                deliver = True
    if deliver:
        try:
            mail_delivery.send_mail(account[1], 'AMRS — password reset code',
                f'Your {role.lower()} password reset code is: {code}\n\n'
                'Enter this code in the AMRS password reset form. It expires in 10 minutes.\n'
                'Do not share this code. If you did not request a reset, ignore this email.\n'
                'Your password has not changed.')
        except Exception:
            with db.connection() as c:
                c.cursor().execute("UPDATE email_password_resets SET status='FAILED',code_hash='!' WHERE request_id=:id AND status='SENDING'", {'id': token})
            raise
        with db.connection() as c:
            c.cursor().execute("UPDATE email_password_resets SET status='SENT' WHERE request_id=:id AND status='SENDING'", {'id': token})
    # Unknown/inactive/limited accounts have the same outward response and opaque token.
    return token


def complete_reset(role, token, code, password):
    _role(role)
    if not re.fullmatch(r'[0-9]{6}', code.strip()):
        raise ValueError('Enter the six-digit code from your email.')
    if len(token) != 36:
        raise ValueError(INVALID)
    new_hash = db.hash_password(password)
    ensure_schema()
    meta = db.one('SELECT user_email FROM email_password_resets WHERE request_id=:id AND user_type=:role', {'id': token, 'role': role})
    if not meta:
        raise ValueError(INVALID)
    changed = False
    with db.connection() as c:
        cur = c.cursor()
        account = _account(cur, role, meta['user_email'].lower())
        cur.execute("""SELECT user_id,code_hash,password_version,attempts,
          CASE WHEN expires_at>SYS_EXTRACT_UTC(SYSTIMESTAMP) THEN 1 ELSE 0 END,status
          FROM email_password_resets WHERE request_id=:id AND user_type=:role FOR UPDATE""", {'id': token, 'role': role})
        row = cur.fetchone()
        if (account and row and row[0] == account[0] and row[2] == account[2]
                and row[3] < 5 and row[4] and row[5] == 'SENT'):
            if db.check_password('AMRS-code:' + code.strip(), row[1]):
                table, col = ('student_logins', 'student_id') if role == 'STUDENT' else ('users', 'user_id')
                cur.execute(f'UPDATE {table} SET password_hash=:pw WHERE {col}=:id AND is_active=1', {'pw': new_hash, 'id': account[0]})
                if cur.rowcount != 1:
                    raise ValueError(INVALID)
                cur.execute("UPDATE email_password_resets SET status='USED',code_hash='!',password_version='!',notification='PENDING',resolved_at=SYS_EXTRACT_UTC(SYSTIMESTAMP) WHERE request_id=:id", {'id': token})
                cur.execute("""UPDATE email_password_resets SET status='INVALIDATED',code_hash='!',password_version='!'
                  WHERE user_type=:role AND user_id=:id AND status IN ('SENDING','SENT')""", {'role': role, 'id': account[0]})
                # A legacy pending request must never overwrite the verified new password.
                cur.execute("""UPDATE password_reset_requests SET status='REJECTED',new_password_hash='!',resolved_at=CURRENT_TIMESTAMP
                  WHERE user_type=:role AND user_id=:id AND status='PENDING'""", {'role': role, 'id': account[0]})
                changed = True
            else:
                cur.execute("""UPDATE email_password_resets SET attempts=attempts+1,
                  status=CASE WHEN attempts>=4 THEN 'LOCKED' ELSE status END,
                  code_hash=CASE WHEN attempts>=4 THEN '!' ELSE code_hash END WHERE request_id=:id""", {'id': token})
    # Raise only AFTER committing a failed attempt, so retries cannot bypass the limit.
    if not changed:
        raise ValueError(INVALID)
    notified = True
    try:
        mail_delivery.send_mail(meta['user_email'], 'AMRS — password reset successful',
            f'Your AMRS {role.lower()} password has been reset successfully.\n'
            'You can now sign in using your new password.\n'
            'If you did not make this change, contact your university administrator immediately.\n'
            'AMRS never sends your password by email.')
    except Exception:
        notified = False
    # A delivery/audit failure after commit must not report the password change as failed.
    try:
        with db.connection() as c:
            c.cursor().execute('UPDATE email_password_resets SET notification=:state WHERE request_id=:id', {'state': 'SENT' if notified else 'FAILED', 'id': token})
    except Exception:
        pass
    return notified
