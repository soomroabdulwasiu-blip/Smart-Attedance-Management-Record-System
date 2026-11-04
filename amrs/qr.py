"""HTTPS QR check-in with per-browser, single-use face verification."""

import errno
import hashlib
import ipaddress
import os
import re
import secrets
import socket
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import cv2
import oracledb
from flask import Flask, abort, jsonify, render_template, request, send_from_directory
from werkzeug.serving import ThreadedWSGIServer, WSGIRequestHandler

from . import db
from .config import load
from .qr_face import CameraBusy, FaceResult, QRFaceVerifier
from .qr_tls import reusable_folder, reusable_tls_context, tls_context

ASSETS = Path(__file__).resolve().parent / "qr_assets"
COOKIE = "amrs_qr_ticket"
FRAME_LIMIT = 350_000
SESSION_SECONDS = 900
TICKET_SECONDS = 180
VERIFIED_SECONDS = 45


def public_address(value=None):
    host = (value or "").strip()
    if host:
        if not re.fullmatch(r"[A-Za-z0-9.-]{1,253}", host) or ".." in host:
            raise ValueError(
                "Enter a valid LAN IPv4 address or hostname without a port."
            )
        if re.fullmatch(r"[0-9.]+", host):
            try:
                addr = ipaddress.IPv4Address(host)
                if addr.is_unspecified or addr.is_multicast:
                    raise ValueError()
            except ValueError:
                raise ValueError("Enter a valid reachable IPv4 address.") from None
        elif any(
            not part or len(part) > 63 or part.startswith("-") or part.endswith("-")
            for part in host.split(".")
        ):
            raise ValueError("Enter a valid hostname.")
        return host
    candidates = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            candidates.append(sock.getsockname()[0])
    except OSError:
        pass
    try:
        candidates.extend(
            info[4][0]
            for info in socket.getaddrinfo(
                socket.gethostname(), None, socket.AF_INET, socket.SOCK_STREAM
            )
        )
    except OSError:
        pass
    for candidate in candidates:
        try:
            addr = ipaddress.ip_address(candidate)
            if not addr.is_loopback and not addr.is_unspecified:
                return candidate
        except ValueError:
            continue
    raise ValueError(
        "Could not detect a LAN address. Enter this computer’s Wi-Fi IPv4 address in the QR settings."
    )


class QuietQRHandler(WSGIRequestHandler):
    def log_request(self, code="-", size="-"):
        # URLs contain live session tokens, so avoid writing them to access logs.
        pass


class QRBindError(RuntimeError):
    def __init__(self, error):
        self.code = error.winerror if getattr(error, "winerror", None) else error.errno
        super().__init__("QR listener could not bind")


class ExclusiveQRServer(ThreadedWSGIServer):
    # On Windows SO_REUSEADDR permits a second listener to steal the same port.
    allow_reuse_address = os.name != "nt"

    def server_bind(self):
        try:
            if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            return super().server_bind()
        except OSError as exc:
            raise QRBindError(exc) from None


def listen(host, port, app, tls):
    alternatives = (*range(port, min(port + 5, 65536)), 0) if port else (0,)
    for candidate in alternatives:
        try:
            return ExclusiveQRServer(
                host, candidate, app, handler=QuietQRHandler, ssl_context=tls
            )
        except QRBindError as exc:
            if exc.code not in {errno.EADDRINUSE, errno.EACCES, 10048, 10013}:
                raise ValueError(
                    f"QR address {host} is unavailable on this laptop. Check the Wi-Fi connection."
                ) from None
        except OSError, SystemExit:
            raise RuntimeError(
                "Could not start the secure QR listener. Check the Wi-Fi and HTTPS settings."
            ) from None
    raise RuntimeError(
        "No QR port could be opened on this network. Check the Windows firewall or ask IT."
    )


@dataclass
class Ticket:
    student: dict
    deadline: float
    poses: tuple = field(
        default_factory=lambda: ("center", secrets.choice(("left", "right")))
    )
    step: int = 0
    frame_count: int = 0
    failures: int = 0
    next_frame: float = 0
    verified_until: float = 0
    verified_box: tuple[float, float, float, float] | None = None
    busy: bool = False
    seen: set = field(default_factory=set)


def reply(message, status=200, **data):
    return jsonify(message=message, **data), status


class QRCheckin:
    def __init__(self, user, course, day, token, verifier, course_label=None):
        self.user, self.course, self.day, self.token = user, course, day, token
        self.verifier = verifier
        self.course_label = course_label
        self.path = "/checkin/" + token
        self.deadline = time.monotonic() + SESSION_SECONDS
        self.lock = threading.RLock()
        self.auth_slots = threading.BoundedSemaphore(4)
        self.tickets = {}
        self.attempts = {}
        self.origin = ""
        self.app = self.build_app()

    def close(self):
        with self.lock:
            self.deadline = 0
            self.tickets.clear()

    def expire_tickets(self, now):
        for key, ticket in list(self.tickets.items()):
            if now >= ticket.deadline:
                del self.tickets[key]

    def build_app(self):
        app = Flask(__name__, static_folder=None, template_folder=str(ASSETS))
        app.config["MAX_CONTENT_LENGTH"] = FRAME_LIMIT

        @app.after_request
        def secure_headers(response):
            response.headers.update(
                {
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                    "Referrer-Policy": "no-referrer",
                    "Permissions-Policy": "camera=(self), microphone=(), geolocation=()",
                    "Content-Security-Policy": "default-src 'none'; style-src 'self'; script-src 'self'; connect-src 'self'; media-src 'self' blob:; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
                }
            )
            return response

        @app.before_request
        def protect():
            if not request.is_secure or request.host != self.origin.removeprefix(
                "https://"
            ):
                return reply(
                    "Use the trusted HTTPS link from the teacher’s QR code.", 400
                )
            if time.monotonic() >= self.deadline:
                return reply(
                    "This QR session has ended. Ask your teacher for a new code.", 410
                )
            if (
                request.method == "POST"
                and request.headers.get("Origin") != self.origin
            ):
                return reply("Open the original AMRS check-in page and try again.", 403)
            return None

        @app.get(self.path)
        def checkin():
            return render_template(
                "index.html",
                course=self.course_label,
                day=self.day.strftime("%d %b %Y"),
            )

        @app.get(self.path + "/assets/<name>")
        def asset(name):
            if name not in ("checkin.css", "checkin.js"):
                abort(404)
            return send_from_directory(ASSETS, name)

        app.add_url_rule(self.path + "/login", view_func=self.login, methods=["POST"])
        app.add_url_rule(self.path + "/verify", view_func=self.verify, methods=["POST"])
        app.add_url_rule(self.path + "/mark", view_func=self.mark, methods=["POST"])
        return app

    def allow_login(self, ip, identity):
        now = time.monotonic()
        with self.lock:
            for key, times in list(self.attempts.items()):
                while times and now - times[0] >= 60:
                    times.popleft()
                if not times:
                    del self.attempts[key]
            keys = ("ip:" + ip, "account:" + identity.casefold())
            if (
                len(self.attempts) + sum(key not in self.attempts for key in keys)
                > 1024
            ):
                return False
            if any(
                len(self.attempts.get(key, ())) >= limit
                for key, limit in zip(keys, (24, 6))
            ):
                return False
            for key in keys:
                self.attempts.setdefault(key, deque()).append(now)
            return True

    def login(self):
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return reply("Enter your roll number and password.", 400)
        roll, password = data.get("roll"), data.get("password")
        if not isinstance(roll, str) or not isinstance(password, str):
            return reply("Enter your roll number and password.", 400)
        roll = roll.strip()
        try:
            password_bytes = len(password.encode())
            roll.encode()
        except UnicodeError:
            return reply("Check your roll number and password.", 400)
        if not 1 <= len(roll) <= 64 or not 1 <= password_bytes <= 72:
            return reply("Check your roll number and password.", 400)
        if not self.allow_login(request.remote_addr or "unknown", roll):
            return reply("Too many sign-in attempts. Wait one minute.", 429)
        if not self.auth_slots.acquire(blocking=False):
            return reply("Several students are signing in. Try again in a moment.", 503)
        try:
            user = db.login("STUDENT", roll, password)
            student = db.qr_face_student(self.course, user["user_id"])
        except ValueError:
            return reply("Sign-in failed. Check your roll number and password.", 401)
        except oracledb.Error, RuntimeError, OSError:
            return reply("Sign-in is temporarily unavailable. Try again.", 503)
        finally:
            self.auth_slots.release()
        if not student:
            return reply(
                "An active course enrollment and a consented face are required. Ask your teacher.",
                403,
            )
        with self.lock:
            now = time.monotonic()
            if now >= self.deadline:
                return reply("This QR session has ended.", 410)
            self.expire_tickets(now)
            self.tickets.pop(request.cookies.get(COOKIE), None)
            if len(self.tickets) >= 256:
                return reply("The check-in queue is full. Try again shortly.", 503)
            key = secrets.token_urlsafe(32)
            ticket = self.tickets[key] = Ticket(
                student, min(self.deadline, now + TICKET_SECONDS)
            )
        response = jsonify(
            message="Sign-in complete. Verify your enrolled face.", pose=ticket.poses[0]
        )
        response.set_cookie(
            COOKIE,
            key,
            max_age=TICKET_SECONDS,
            secure=True,
            httponly=True,
            samesite="Strict",
            path=self.path,
        )
        return response

    def verify(self):
        if (
            request.mimetype != "image/jpeg"
            or not request.content_length
            or request.content_length > FRAME_LIMIT
        ):
            return reply("A valid camera frame is required.", 400)
        raw = request.get_data(cache=False)
        if not raw:
            return reply("No camera frame was received.", 400)
        key = request.cookies.get(COOKIE)
        digest = hashlib.sha256(raw).digest()
        now = time.monotonic()
        with self.lock:
            self.expire_tickets(now)
            ticket = self.tickets.get(key)
            if not ticket:
                return reply("Sign in again to verify your face.", 401)
            if ticket.verified_until:
                if now < ticket.verified_until:
                    return reply(
                        "Face verified. Mark attendance to finish.",
                        verified=True,
                        validForMs=int((ticket.verified_until - now) * 1000),
                        faceStatus="verified",
                        faceBox=ticket.verified_box,
                    )
                self.tickets.pop(key, None)
                return reply("Face verification expired. Sign in again.", 410)
            if ticket.busy or now < ticket.next_frame:
                return reply(
                    "Hold your position. Checking the camera.", 429, retry=True
                )
            if ticket.frame_count >= 64 or ticket.failures >= 4:
                self.tickets.pop(key, None)
                return reply(
                    "Face verification did not complete. Sign in again or ask your teacher.",
                    403,
                )
            ticket.next_frame = now + 0.22
            if digest in ticket.seen:
                return reply(
                    "Keep your face in view and follow the movement prompt.",
                    pose=ticket.poses[ticket.step],
                )
            ticket.frame_count += 1
            ticket.busy = True
            pose = ticket.poses[ticket.step]
        try:
            evidence = self.verifier.verify(raw, ticket.student, pose)
        except CameraBusy:
            evidence = FaceResult("busy")
        except ValueError:
            evidence = FaceResult("frame")
        except oracledb.Error, cv2.error, RuntimeError, OSError:
            evidence = FaceResult("unavailable")
        result = evidence.status
        feedback = {"faceBox": evidence.box}
        with self.lock:
            ticket.busy = False
            now = time.monotonic()
            if self.tickets.get(key) is not ticket or now >= min(
                ticket.deadline, self.deadline
            ):
                return reply("This verification has ended. Sign in again.", 410)
            if result == "match":
                ticket.seen.add(digest)
                ticket.step += 1
                if ticket.step == len(ticket.poses):
                    ticket.verified_until = min(ticket.deadline, now + VERIFIED_SECONDS)
                    ticket.verified_box = evidence.box
                    return reply(
                        "Face verified. Tap Mark attendance to save.",
                        verified=True,
                        validForMs=int((ticket.verified_until - now) * 1000),
                        faceStatus="verified",
                        **feedback,
                    )
                return reply(
                    "Step complete. Follow the next movement prompt.",
                    pose=ticket.poses[ticket.step],
                    step=ticket.step,
                    faceStatus="checking",
                    **feedback,
                )
            if result == "enrollment":
                self.tickets.pop(key, None)
                return reply(
                    "Your enrolled face is unavailable on this computer. Ask your teacher.",
                    403,
                )
            if result == "unavailable":
                return reply(
                    "Face verification is temporarily unavailable. Try again.", 503
                )
            if result == "mismatch":
                ticket.failures += 1
            messages = {
                "busy": "Several students are verifying. Hold your position.",
                "frame": "Adjust the phone and try again.",
                "mismatch": "The face does not match this account.",
                "one_face": "Keep only your face in view.",
                "closer": "Move closer and face the light.",
                "pose": "Follow the movement prompt.",
            }
            return reply(
                messages.get(result, "Try again."),
                pose=pose,
                step=ticket.step,
                faceStatus="mismatch" if result == "mismatch" else "checking",
                **feedback,
            )

    def mark(self):
        key = request.cookies.get(COOKIE)
        with self.lock:
            now = time.monotonic()
            ticket = self.tickets.get(key)
            if (
                not ticket
                or ticket.busy
                or not now < min(ticket.verified_until, ticket.deadline, self.deadline)
            ):
                return reply("Verify your face before marking attendance.", 403)
            # Consume the verified ticket before the Oracle write. Reloading or
            # clicking twice cannot submit it again, even when a write fails.
            del self.tickets[key]
            try:
                saved = db.mark_verified_qr(
                    self.user,
                    self.course,
                    ticket.student["student_id"],
                    self.day,
                    self.token,
                )
            except ValueError:
                return reply(
                    "Attendance could not be saved. Ask your teacher to review your record.",
                    409,
                )
            except oracledb.Error, RuntimeError, OSError:
                return reply(
                    "Could not confirm the save. Sign in again or ask your teacher.",
                    503,
                )
        return reply(
            "Attendance marked successfully."
            if saved
            else "Your attendance was already recorded.",
            saved=True,
        )


class QRServer:
    def __init__(
        self, user, course, day, port=8090, public_host=None, course_label=None
    ):
        db.require_actor(user, ("TEACHER",))
        if day > datetime.now().date():
            raise ValueError("Future attendance is not allowed.")
        config = load()
        reusable = reusable_folder(config.qr_cert_file, config.qr_key_file)
        if reusable:
            # The saved address was the setup address. Use the current route on each new session.
            override = (public_host or "").strip()
            host = public_address(
                override if override != config.qr_public_host else None
            ).lower()
            tls = reusable_tls_context(reusable, host)
        else:
            host = public_address(public_host or config.qr_public_host).lower()
            if config.qr_cert_file and re.fullmatch(r"[0-9.]+", host):
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                    try:
                        probe.bind((host, 0))
                    except OSError:
                        raise ValueError(
                            f"Saved QR address {host} is no longer on this laptop. Open HTTPS setup and create a reusable classroom certificate."
                        ) from None
            tls = tls_context(config.qr_cert_file, config.qr_key_file, host)
        self.token = secrets.token_urlsafe(24)
        self.checkin = QRCheckin(
            user,
            course,
            day,
            self.token,
            QRFaceVerifier(config.face_threshold),
            course_label,
        )
        self.server = listen(host, port, self.checkin.app, tls)
        self.host = host
        self.port = self.server.server_port
        suffix = "" if self.server.server_port == 443 else f":{self.server.server_port}"
        self.checkin.origin = f"https://{host}{suffix}"
        self.url = self.checkin.origin + self.checkin.path
        try:
            with db.connection() as c:
                cur = c.cursor()
                cur.execute(
                    """INSERT INTO checkin_sessions(session_token,course_id,session_date,teacher_id,expires_at)
                    SELECT :token,c.course_id,:day,:teacher,CAST(SYSDATE AS TIMESTAMP) + INTERVAL '15' MINUTE
                    FROM courses c JOIN users u ON u.user_id=c.teacher_id JOIN roles r ON r.role_id=u.role_id
                    WHERE c.course_id=:course AND c.teacher_id=:teacher AND c.is_active=1 AND u.is_active=1
                    AND r.role_name='TEACHER' """,
                    {
                        "token": self.token,
                        "course": course,
                        "day": day,
                        "teacher": user["user_id"],
                    },
                )
                if cur.rowcount != 1:
                    raise ValueError(
                        "Only the assigned active teacher can create this QR session."
                    )
        except Exception:
            self.server.server_close()
            raise
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        self.checkin.close()
        self.server.shutdown()
        self.thread.join(timeout=3)
        self.server.server_close()
