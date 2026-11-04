"""Deterministic camera/transport tests; no camera, LAN, database or face files."""

import threading
from dataclasses import replace

import cv2
import numpy as np
import pytest
import requests

from amrs.cameras import (
    CameraConfig,
    ESP32CAMStreamAdapter,
    HTTPMJPEGCapture,
    LocalCameraAdapter,
    MockCameraAdapter,
    RaspberryPiStreamAdapter,
    RTSPCameraAdapter,
    USBCameraAdapter,
    create_adapter,
    discover_devices,
    discover_simulated_devices,
    valid_frame,
    validate_config,
    validate_endpoint,
)


def config(kind="usb", source="1", **kwargs):
    return CameraConfig("test-device", "Test camera", kind, source, **kwargs)


@pytest.mark.parametrize(
    "source",
    [
        "http://127.0.0.1/stream",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/stream",
        "http://[::ffff:127.0.0.1]/stream",
        "http://0.0.0.0/stream",
        "rtsp://224.0.0.1/live",
        "http://192.168.1.1:1521/stream",
        "http://camera.local/stream",
        "rtsp://user:private-password@192.168.1.5/live",
        "http://192.168.1.5/stream?token=private-token",
        "http://192.168.1.5/stream#private",
        "file:///etc/passwd",
        "http://192.168.1.5/stream%0d%0aHeader",
        "http://192.168.1.5:999999/stream",
        "http://2130706433/stream",
        "http://192.168.1.5:0/stream",
    ],
)
def test_rejects_sensitive_or_credential_bearing_endpoints(source):
    with pytest.raises(ValueError) as error:
        validate_endpoint(source, allow_private_network=True)
    assert "private-password" not in str(error.value)
    assert "private-token" not in str(error.value)


def test_lan_requires_specific_administrator_opt_in():
    with pytest.raises(ValueError, match="authorize"):
        validate_endpoint("rtsp://192.168.1.25:8554/classroom")
    assert (
        validate_endpoint(
            "rtsp://192.168.1.25:8554/classroom", allow_private_network=True
        )
        == "rtsp://192.168.1.25:8554/classroom"
    )
    assert validate_endpoint(
        "http://10.0.0.25:81/stream", allow_private_network=True
    ).endswith(":81/stream")


@pytest.mark.parametrize(
    "changes",
    [
        {"open_timeout_ms": 0},
        {"read_timeout_ms": 100000},
        {"reconnect_attempts": 999},
        {"retry_delay_ms": -1},
        {"allow_private_network": "yes"},
        {"source": "-1"},
        {"source": "32"},
        {"device_type": "arbitrary"},
        {"name": "\nprivate"},
        {"device_id": "../../unsafe"},
    ],
)
def test_invalid_config_refused_without_capture(changes):
    with pytest.raises(ValueError):
        validate_config(replace(config(), **changes))


class Capture:
    def __init__(self, opened=True, frame=None):
        self.opened = opened
        self.frame = np.zeros((48, 64, 3), dtype=np.uint8) if frame is None else frame
        self.released = False

    def isOpened(self):
        return self.opened

    def read(self):
        return self.opened, self.frame.copy()

    def release(self):
        self.released = True
        self.opened = False


def test_local_camera_lifecycle_measures_frames_without_invented_metadata():
    raw = Capture()
    calls = []
    adapter = create_adapter(
        config(), capture_factory=lambda *args: (calls.append(args), raw)[1]
    )
    assert isinstance(adapter, USBCameraAdapter)
    assert adapter.get_device_info()["resolution"] is None
    assert adapter.get_device_info()["fps"] is None
    assert not adapter.isOpened()
    assert adapter.connect()
    assert calls[0][0] == 1
    assert adapter.read()[0]
    assert adapter.get_device_info()["resolution"] == (64, 48)
    assert adapter.get_connection_status()["last_connected"] is not None
    adapter.release()
    adapter.release()
    assert raw.released and not adapter.is_connected()


def test_network_capture_uses_open_and_read_timeouts_and_releases_on_failure():
    calls = []
    capture = Capture()
    adapter = create_adapter(
        config("rtsp", "rtsp://10.0.0.5/live", allow_private_network=True),
        capture_factory=lambda *args: (calls.append(args), capture)[1],
    )
    assert isinstance(adapter, RTSPCameraAdapter) and adapter.connect()
    assert calls[0][1] == cv2.CAP_FFMPEG
    assert calls[0][2] == [
        cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,
        5000,
        cv2.CAP_PROP_READ_TIMEOUT_MSEC,
        3000,
    ]
    capture.opened = False
    assert adapter.read() == (False, None)
    assert capture.released and adapter.get_connection_status()["state"] == "error"


def test_corrupt_frames_do_not_reach_recognition():
    capture = Capture(frame=np.zeros((48, 64), dtype=np.uint8))
    adapter = create_adapter(config(), capture_factory=lambda *args: capture)
    assert adapter.connect()
    assert adapter.read() == (False, None)
    assert capture.released
    assert not valid_frame(np.zeros((1, 1, 3), dtype=np.uint8))
    assert not valid_frame(np.zeros((48, 64, 3), dtype=float))


def test_reconnect_is_bounded_and_cancellation_prevents_open():
    calls = []
    adapter = create_adapter(
        config(reconnect_attempts=3, retry_delay_ms=0),
        capture_factory=lambda *args: (calls.append(args), Capture(False))[1],
    )
    assert not adapter.reconnect()
    assert len(calls) == 3
    stop = threading.Event()
    stop.set()
    assert not adapter.reconnect(stop)
    assert len(calls) == 3


def test_connection_exception_does_not_expose_driver_message():
    def fail(*args):
        raise RuntimeError("private-password private-token")

    adapter = create_adapter(config(), capture_factory=fail)
    assert not adapter.connect()
    assert "private" not in adapter.get_connection_status()["last_error"]


def test_authenticated_rtsp_refused_before_native_capture_can_log_password():
    calls = []
    adapter = create_adapter(
        config("rtsp", "rtsp://10.0.0.5/live", allow_private_network=True),
        credentials={"username": "user", "password": "private-password"},
        capture_factory=lambda *args: calls.append(args),
    )
    assert not adapter.connect() and not calls
    assert "gateway" in adapter.get_connection_status()["last_error"]
    assert "private-password" not in str(adapter.get_connection_status())


@pytest.mark.parametrize(
    "kind,source,expected",
    [
        ("builtin", "0", LocalCameraAdapter),
        ("usb", "1", USBCameraAdapter),
        ("raspberry_pi", "rtsp://192.168.1.5:8554/cam", RaspberryPiStreamAdapter),
        ("esp32", "http://192.168.1.5:81/stream", ESP32CAMStreamAdapter),
        ("mock", "mock://classroom", MockCameraAdapter),
    ],
)
def test_factory_selects_same_interface_for_supported_types(kind, source, expected):
    adapter = create_adapter(config(kind, source, allow_private_network=True))
    assert isinstance(adapter, expected)
    assert all(
        callable(getattr(adapter, name))
        for name in (
            "connect",
            "disconnect",
            "is_connected",
            "read_frame",
            "get_device_info",
            "get_connection_status",
            "reconnect",
            "release",
        )
    )
    adapter.release()


def test_discovery_releases_every_probed_camera_and_obeys_cancellation():
    captures = []

    def factory(index, backend):
        capture = Capture(opened=index == 1)
        captures.append(capture)
        return capture

    devices = discover_devices(3, capture_factory=factory)
    assert [item.source for item in devices] == ["1"]
    assert all(item.released for item in captures)
    stop = threading.Event()
    stop.set()
    assert discover_devices(3, capture_factory=factory, cancel_event=stop) == []
    assert len(captures) == 3


def test_simulated_discovery_switching_and_recovery_are_explicitly_labeled():
    devices = discover_simulated_devices()
    assert len(devices) == 3 and all(
        item.name.startswith("SIMULATED") for item in devices
    )
    first = create_adapter(replace(devices[0], simulation_profile="interruption"))
    assert first.connect()
    assert all(first.read()[0] for _ in range(3))
    assert first.read() == (False, None)
    assert first.reconnect() and first.read()[0]
    assert first.get_device_info()["simulated"] is True
    first.release()
    second = create_adapter(devices[1])
    assert second.connect() and second.read()[0]
    assert second.get_device_info()["device_id"] != first.get_device_info()["device_id"]
    second.release()


def test_mock_failures_and_invalid_configuration():
    adapter = create_adapter(
        config("mock", "mock://test", simulation_profile="corrupt")
    )
    assert adapter.connect()
    assert all(adapter.read()[0] for _ in range(3))
    assert adapter.read() == (False, None)
    assert adapter.reconnect() and adapter.read()[0]
    adapter.inject_failure("disconnect")
    assert adapter.read() == (False, None)
    adapter.inject_failure("connect")
    assert not adapter.connect()
    assert adapter.reconnect()
    adapter.release()
    with pytest.raises(ValueError):
        create_adapter(config("mock", "file://private", simulation_profile="normal"))
    with pytest.raises(ValueError):
        create_adapter(config("mock", "mock://test", simulation_profile="invalid"))


def test_mock_next_connect_failure_survives_reads_until_connection_attempt():
    adapter = create_adapter(config("mock", "mock://test"))
    assert adapter.connect()
    adapter.inject_failure("connect")
    assert adapter.read()[0]
    assert not adapter.connect()
    assert adapter.connect()
    adapter.release()


class Response:
    def __init__(self, status=200, content_type="multipart/x-mixed-replace", chunks=()):
        self.status_code = status
        self.headers = {"Content-Type": content_type}
        self.chunks = chunks
        self.closed = False

    def iter_content(self, chunk_size):
        return iter(self.chunks)

    def close(self):
        self.closed = True


class Session:
    def __init__(self, response):
        self.response = response
        self.calls = []
        self.closed = False
        self.trust_env = True

    def get(self, source, **kwargs):
        self.calls.append((source, kwargs))
        return self.response

    def close(self):
        self.closed = True


def test_http_jpeg_transport_headers_authentication_tls_and_resource_cleanup(
    monkeypatch,
):
    _, encoded = cv2.imencode(".jpg", np.full((48, 64, 3), 70, dtype=np.uint8))
    raw = encoded.tobytes()
    response = Response(chunks=[b"--frame\r\n", raw[:50], raw[50:]])
    session = Session(response)
    monkeypatch.setattr(requests, "Session", lambda: session)
    adapter = create_adapter(
        config("http", "https://10.0.0.5/stream", allow_private_network=True),
        credentials={
            "username": "test-user",
            "password": "private-password",
            "mode": "digest",
        },
    )
    assert adapter.connect() and adapter.read()[0]
    source, options = session.calls[0]
    assert source == "https://10.0.0.5/stream" and "private-password" not in source
    assert options["verify"] is True and options["allow_redirects"] is False
    assert options["timeout"] == (5, 3)
    assert isinstance(options["auth"], requests.auth.HTTPDigestAuth)
    assert not session.trust_env
    assert "private-password" not in str(adapter.get_device_info())
    adapter.release()
    assert response.closed and session.closed


@pytest.mark.parametrize(
    "status,media", [(302, "text/html"), (200, "text/html"), (401, "text/html")]
)
def test_http_rejects_redirects_login_pages_and_authentication_errors(
    monkeypatch, status, media
):
    response = Response(status=status, content_type=media)
    session = Session(response)
    monkeypatch.setattr(requests, "Session", lambda: session)
    adapter = create_adapter(
        config("http", "http://10.0.0.5/stream", allow_private_network=True)
    )
    assert not adapter.connect()
    assert session.calls[0][1]["allow_redirects"] is False
    assert response.closed and session.closed


def test_http_size_limit_and_stream_interruption_close_resources(monkeypatch):
    response = Response(chunks=[b"x" * (2 * 1024 * 1024 + 1)])
    session = Session(response)
    monkeypatch.setattr(requests, "Session", lambda: session)
    capture = HTTPMJPEGCapture(
        config("http", "http://10.0.0.5/stream", allow_private_network=True)
    )
    assert capture.isOpened()
    assert capture.read() == (False, None)
    assert "2 MiB" in capture.error
    assert response.closed and session.closed


def test_http_network_exception_redacts_details(monkeypatch):
    class FailingSession(Session):
        def get(self, source, **kwargs):
            raise requests.ConnectionError("private-password private-token")

    session = FailingSession(Response())
    monkeypatch.setattr(requests, "Session", lambda: session)
    adapter = create_adapter(
        config("http", "http://10.0.0.5/stream", allow_private_network=True)
    )
    assert not adapter.connect()
    assert "private" not in adapter.get_connection_status()["last_error"]
    assert session.closed
