"""Regression tests for the browser/Oracle boundary of secured QR attendance."""

import io
import os
import socket
import ssl
import time
import uuid
from datetime import date

import numpy as np
import pytest
import requests
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from PIL import Image

from amrs import db, privacy, qr
from amrs.qr_face import FaceResult, QRFaceVerifier
from amrs.qr_tls import (
    create_reusable_certificate,
    make_local_certificate,
    reusable_tls_context,
    tls_context,
)

ORIGIN = "https://192.168.1.44:8090"
TEACHER = {"role": "TEACHER", "user_id": "T"}
STUDENT = {"student_id": "S", "roll_number": "ROLL", "face_enrolled": 1}


class FixtureVerifier:
    def verify(self, raw, student, pose):
        return FaceResult(
            "match" if raw.startswith(pose.encode() + b":") else "mismatch",
            (0.25, 0.20, 0.45, 0.55),
        )


@pytest.fixture
def browser(monkeypatch):
    attempts = []
    session = qr.QRCheckin(
        TEACHER, "C", date.today(), "qr-demo-token", FixtureVerifier()
    )
    session.origin = ORIGIN
    client = session.app.test_client()

    def login(role, roll, password):
        if (role, roll, password) != ("STUDENT", "ROLL", "example password"):
            raise ValueError("Wrong credentials")
        return {"user_id": "S"}

    monkeypatch.setattr(db, "login", login)
    monkeypatch.setattr(db, "qr_face_student", lambda course, student: STUDENT)
    monkeypatch.setattr(
        db, "mark_verified_qr", lambda *args: attempts.append(args) or True
    )

    def post(action, *, caller=client, origin=ORIGIN, **kwargs):
        return caller.post(
            session.path + "/" + action,
            base_url=ORIGIN,
            headers={"Origin": origin},
            **kwargs,
        )

    def sign_in():
        result = post("login", json={"roll": "ROLL", "password": "example password"})
        assert result.status_code == 200
        assert all(
            item in result.headers["Set-Cookie"]
            for item in ("Secure", "HttpOnly", "SameSite=Strict")
        )
        return next(iter(session.tickets.values()))

    def frame(raw):
        for ticket in session.tickets.values():
            ticket.next_frame = 0
        return post("verify", data=raw, content_type="image/jpeg")

    return session, client, post, sign_in, frame, attempts


def test_no_mark_until_server_verifies_and_ticket_cannot_be_shared(browser):
    session, client, post, sign_in, frame, attempts = browser
    assert (
        client.post(
            session.path,
            base_url=ORIGIN,
            data={"roll": "ROLL", "password": "example password"},
        ).status_code
        == 403
    )
    assert post("mark").status_code == 403
    ticket = sign_in()
    assert post("mark", json={"verified": True, "student": "OTHER"}).status_code == 403
    rejected = frame(b"wrong-person").json
    assert rejected["faceStatus"] == "mismatch" and rejected["faceBox"]
    assert rejected.get("verified") is None
    assert not attempts
    for index, pose in enumerate(ticket.poses):
        response = frame(f"{pose}:{index}".encode())
        assert response.status_code == 200
        assert bool(response.json.get("verified")) == (index == len(ticket.poses) - 1)
    assert response.json["faceStatus"] == "verified" and response.json["faceBox"]
    assert post("mark", caller=session.app.test_client()).status_code == 403
    assert post("mark", origin="https://attacker.test").status_code == 403
    assert post("mark", json={"student": "OTHER"}).json["saved"]
    assert len(attempts) == 1 and attempts[0][2] == "S"
    assert post("mark").status_code == 403


def test_replay_expiry_wrong_host_and_stop(browser):
    session, client, post, sign_in, frame, attempts = browser
    assert client.get(session.path, base_url=ORIGIN).status_code == 200
    assert (
        client.get(session.path, base_url=ORIGIN.replace("https:", "http:")).status_code
        == 400
    )
    assert client.get(session.path, base_url="https://other.test").status_code == 400
    assert client.get("/checkin/bad", base_url=ORIGIN).status_code == 404
    ticket = sign_in()
    frame(b"center:1")
    assert not frame(b"center:1").json.get("verified")
    assert frame(f"{ticket.poses[1]}:2".encode()).json["verified"]
    ticket.verified_until = time.monotonic() - 1
    assert post("mark").status_code == 403
    session.close()
    assert post("mark").status_code == 410
    assert not attempts


def test_mismatch_rate_limit_and_body_limit(browser):
    _, _, post, sign_in, frame, attempts = browser
    for _ in range(6):
        assert (
            post("login", json={"roll": "BAD", "password": "wrong"}).status_code == 401
        )
    assert post("login", json={"roll": "bad", "password": "wrong"}).status_code == 429
    sign_in()
    assert frame(b"x" * (qr.FRAME_LIMIT + 1)).status_code in (400, 413)
    for _ in range(4):
        assert not frame(b"wrong").json.get("verified")
    assert frame(b"center:now").status_code == 403
    assert post("mark").status_code == 403
    assert not attempts


def test_real_face_decision_rejects_wrong_embedding_and_multiple_faces(monkeypatch):
    good = np.zeros(128, dtype="float32")
    good[0] = 1
    wrong = np.roll(good, 1)
    landmarks = np.array([20, 20, 120, 140, 40, 55, 100, 55, 70, 80], dtype="float32")

    class Engine:
        def __init__(self):
            self.faces = [landmarks]
            self.embedding = good

        def load_references(self, students):
            return [(students[0], good)], []

        def detect(self, frame):
            assert frame.shape == (240, 320, 3)
            return self.faces

        def encode(self, frame, face):
            return self.embedding

    monkeypatch.setattr("amrs.qr_face.FaceEngine", Engine)
    verifier = QRFaceVerifier(0.55)
    with io.BytesIO() as output:
        Image.new("RGB", (320, 240)).save(output, format="JPEG")
        jpeg = output.getvalue()
    student = dict(STUDENT)
    assert verifier.verify(jpeg, student, "center").status == "match"
    assert verifier.verify(jpeg, student, "left").status == "pose"
    verifier.engine.embedding = wrong
    assert verifier.verify(jpeg, student, "left").status == "mismatch"
    verifier.engine.faces = [landmarks, landmarks]
    assert verifier.verify(jpeg, student, "center").status == "one_face"


def test_reusable_tls_keeps_same_phone_root_and_busy_port_recovers(
    monkeypatch, tmp_path
):
    from flask import Flask

    from amrs import qr_tls

    monkeypatch.setenv("AMRS_PROFILE_DIR", str(tmp_path))
    monkeypatch.setattr(qr_tls, "PRIVATE_NETWORKS", ("127.0.0.0/8",))
    cert, _, phone, _ = create_reusable_certificate("127.0.0.1")
    root = x509.load_der_x509_certificate(phone.read_bytes())
    trust = tmp_path / "test-ca.pem"
    trust.write_bytes(root.public_bytes(serialization.Encoding.PEM))
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        preferred = busy.getsockname()[1]
        app = Flask(__name__)
        app.get("/")(lambda: "QR ready")
        first = qr.listen(
            "127.0.0.1", preferred, app, reusable_tls_context(cert.parent, "127.0.0.1")
        )
        assert first.server_port != preferred
        first.server_close()
    # Renew under the same exported root, then complete an HTTPS request on
    # the new address. This also verifies that the intermediate is sent.
    import threading

    next_host = "127.0.0.2"
    tls = reusable_tls_context(cert.parent, next_host)
    listener = qr.listen(next_host, 0, app, tls)
    thread = threading.Thread(target=listener.serve_forever, daemon=True)
    thread.start()
    try:
        with requests.Session() as client:
            client.trust_env = False
            assert (
                client.get(
                    f"https://{next_host}:{listener.server_port}/",
                    verify=str(trust),
                    timeout=5,
                ).text
                == "QR ready"
            )
    finally:
        listener.shutdown()
        thread.join(timeout=3)
        listener.server_close()
    assert phone.read_bytes() == root.public_bytes(serialization.Encoding.DER)


def test_local_certificate_is_limited_and_rejects_wrong_address(monkeypatch, tmp_path):
    monkeypatch.setenv("AMRS_PROFILE_DIR", str(tmp_path))
    cert, key, phone, _ = make_local_certificate("192.168.1.44")
    root = x509.load_der_x509_certificate(phone.read_bytes())
    leaf = x509.load_pem_x509_certificate(cert.read_bytes())
    leaf.verify_directly_issued_by(root)
    root_scope = root.extensions.get_extension_for_class(x509.NameConstraints)
    assert (
        root_scope.critical
        and str(root_scope.value.permitted_subtrees[0].value) == "192.168.1.44/32"
    )
    assert sorted(p.name for p in cert.parent.iterdir()) == [
        "AMRS-QR-Trust.cer",
        "server-key.pem",
        "server.pem",
    ]
    assert (
        tls_context(cert, key, "192.168.1.44").minimum_version == ssl.TLSVersion.TLSv1_2
    )
    with pytest.raises(ValueError, match="does not cover"):
        tls_context(cert, key, "192.168.1.45")


@pytest.mark.oracle
@pytest.mark.skipif(
    os.getenv("AMRS_TEST_ORACLE") != "1", reason="Requires disposable Oracle schemas"
)
def test_native_https_and_oracle_save(monkeypatch, tmp_path):
    monkeypatch.setenv("AMRS_PROFILE_DIR", str(tmp_path))
    # Exercise the same certificate chain on loopback without involving a phone trust store.
    original_network = qr.ipaddress.ip_network
    with monkeypatch.context() as local:
        local.setattr(
            "amrs.qr_tls.ipaddress.ip_network",
            lambda net: original_network("127.0.0.0/8" if net == "10.0.0.0/8" else net),
        )
        cert, key, phone, _ = make_local_certificate("127.0.0.1")
    root = x509.load_der_x509_certificate(phone.read_bytes())
    pem = tmp_path / "test-trust.pem"
    pem.write_bytes(root.public_bytes(serialization.Encoding.PEM))
    monkeypatch.setenv("AMRS_QR_CERT_FILE", str(cert))
    monkeypatch.setenv("AMRS_QR_KEY_FILE", str(key))
    monkeypatch.setattr(qr, "QRFaceVerifier", lambda threshold: FixtureVerifier())
    admin = dict(
        db.one("""SELECT u.user_id FROM users u JOIN roles r ON r.role_id=u.role_id
        WHERE r.role_name='ADMIN' FETCH FIRST 1 ROWS ONLY"""),
        role="ADMIN",
    )
    tag = uuid.uuid4().hex[:9].upper()
    dept = db.departments()[0]["dept_id"]
    pw = "Synthetic-fixture-123"
    db.signup_teacher(
        "QR Teacher", f"{tag}-t@example.test", pw, "Test department", actor=admin
    )
    teacher = db.login("TEACHER", f"{tag}-t@example.test", pw)
    db.signup_student("QR Student", f"{tag}-s@example.test", pw, tag, dept, 1, 2026)
    student = db.login("STUDENT", tag, pw)
    db.add_course(tag, "QR test course", 3, dept, teacher["user_id"], 1, actor=admin)
    course = next(
        row["course_id"] for row in db.courses(teacher) if row["course_code"] == tag
    )
    db.enroll_student(course, student["user_id"], actor=admin)
    privacy.record_consent(admin, student["user_id"], True)
    db.set_face_enrolled(student["user_id"])
    server = qr.QRServer(teacher, course, date.today(), port=0, public_host="127.0.0.1")
    try:
        with requests.Session() as client:
            client.verify = str(pem)
            assert "Secure attendance" in client.get(server.url, timeout=8).text
            client.headers["Origin"] = server.checkin.origin
            post = lambda action, **kwargs: client.post(
                server.url + "/" + action, timeout=8, **kwargs
            )
            assert post("login", json={"roll": tag, "password": pw}).status_code == 200
            assert post("mark").status_code == 403
            assert not db.attendance(student, course)
            ticket = next(iter(server.checkin.tickets.values()))
            for index, pose in enumerate(ticket.poses):
                time.sleep(0.33)
                response = post(
                    "verify",
                    data=f"{pose}:{index}".encode(),
                    headers={"Content-Type": "image/jpeg"},
                )
                assert response.status_code == 200
            assert response.json()["verified"]
            assert post("mark").json()["saved"]
            assert post("mark").status_code == 403
            rows = db.attendance(student, course)
            assert (
                len(rows) == 1
                and rows[0]["status"] == "PRESENT"
                and rows[0]["check_in_method"] == "QR"
            )
            # A verified browser still cannot commit after consent withdrawal.
            assert post("login", json={"roll": tag, "password": pw}).status_code == 200
            ticket = next(iter(server.checkin.tickets.values()))
            for index, pose in enumerate(ticket.poses):
                time.sleep(0.33)
                response = post(
                    "verify",
                    data=f"{pose}:{index}".encode(),
                    headers={"Content-Type": "image/jpeg"},
                )
            assert response.json()["verified"]
            privacy.record_consent(admin, student["user_id"], False)
            assert post("mark").status_code == 409
    finally:
        server.stop()
