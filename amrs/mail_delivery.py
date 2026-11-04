"""Gmail SMTP delivery; local credentials encrypted for the current Windows user."""
import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import smtplib
import ssl
import uuid
from email.message import EmailMessage

from .paths import profile_root

CONFIG_PATH = profile_root() / 'gmail.json'
SETUP_DEFAULTS_PATH = Path(__file__).resolve().parent.parent / 'data' / 'mail_setup.json'


def setup_defaults():
    """Optional non-secret addresses for the first-time setup form."""
    try:
        data = json.loads(SETUP_DEFAULTS_PATH.read_text(encoding='utf-8'))
        return {key: valid_email(data[key]) for key in ('sender', 'recipient')}
    except (OSError, ValueError, KeyError, TypeError):
        return {'sender': '', 'recipient': ''}


def valid_email(value):
    value = value.strip().lower()
    if len(value) > 254 or not re.fullmatch(r'[^\s@<>\r\n]+@[^\s@<>\r\n]+\.[^\s@<>\r\n]+', value):
        raise ValueError('Enter a valid email address.')
    return value


class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def _crypt(data, decrypt=False):
    if os.name != 'nt':
        raise ValueError('Secure local Gmail settings require Windows.')
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                   ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    buf = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise ValueError('Cannot access secure mail settings for this Windows account. Configure Gmail again.')
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel.LocalFree(output.data)


def load_settings():
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
        return valid_email(data['sender']), _crypt(base64.b64decode(data['secret']), True).decode()
    except FileNotFoundError:
        raise ValueError('Email recovery is not configured. Ask the administrator to open Password resets → Gmail settings.') from None
    except (KeyError, TypeError, UnicodeError, json.JSONDecodeError):
        raise ValueError('Mail settings are unreadable. Ask the administrator to configure Gmail again.') from None


def configured_sender():
    try:
        return load_settings()[0]
    except (ValueError, OSError):
        return ''


def _smtp(sender, secret):
    client = smtplib.SMTP_SSL('smtp.gmail.com', 465, context=ssl.create_default_context(), timeout=15)
    try:
        client.login(sender, secret)
        return client
    except Exception:
        client.close()
        raise


def _mail_error(exc):
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return ValueError('Gmail sign-in failed. Check the sender address and Google App Password in Gmail settings.')
    return ValueError('Gmail could not accept the email. Check the internet connection and Gmail settings, then try again.')


def save_settings(sender, secret):
    sender = valid_email(sender)
    secret = secret.replace(' ', '').strip()
    if not re.fullmatch(r'[A-Za-z]{16}', secret):
        raise ValueError('Enter the 16-letter Google App Password, not your normal Gmail password.')
    try:
        client = _smtp(sender, secret)
        client.close()
    except (OSError, smtplib.SMTPException) as exc:
        raise _mail_error(exc) from None
    payload = {'sender': sender, 'secret': base64.b64encode(_crypt(secret.encode())).decode()}
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix('.' + uuid.uuid4().hex + '.tmp')
    try:
        tmp.write_text(json.dumps(payload), encoding='utf-8')
        os.replace(tmp, CONFIG_PATH)
    finally:
        tmp.unlink(missing_ok=True)


def send_mail(recipient, subject, body):
    sender, secret = load_settings()
    msg = EmailMessage()
    msg['From'] = f'AMRS Attendance <{sender}>'
    msg['To'] = valid_email(recipient)
    msg['Subject'] = subject
    msg.set_content(body)
    try:
        client = _smtp(sender, secret)
        try:
            if client.send_message(msg):
                raise smtplib.SMTPException('Recipient refused')
        finally:
            # QUIT failure must not turn an accepted message into an apparent failure.
            client.close()
    except (OSError, smtplib.SMTPException) as exc:
        raise _mail_error(exc) from None


def send_test(recipient):
    send_mail(recipient, 'AMRS — email recovery test',
              'Your AMRS Gmail delivery connection is working.\n'
              'Students and teachers can request a password reset code from their login screen.\n'
              'No account password was changed by this test.')
