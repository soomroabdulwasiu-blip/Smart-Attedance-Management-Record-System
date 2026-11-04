"""Camera adapters shared by preview, enrollment and attendance workers.

Capture is synchronous: adapters belong to a background worker, never the Qt UI
thread. Network open/read operations have bounded timeouts. No adapter stores
credentials, camera footage, face templates, or database records.
"""

from __future__ import annotations

import io
import ipaddress
import os
import re
import threading
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit

import cv2
import numpy as np

DEVICE_TYPES = ("builtin", "usb", "rtsp", "http", "raspberry_pi", "esp32", "mock")
SIMULATION_PROFILES = (
    "normal",
    "interruption",
    "corrupt",
    "connect_failure",
    "low_fps",
)
STREAM_PORTS = frozenset((80, 81, 443, 554, 8000, 8080, 8081, 8554, 8888))
_LAN_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
)


@dataclass(frozen=True)
class CameraConfig:
    device_id: str
    name: str
    device_type: str
    source: str
    allow_private_network: bool = False
    open_timeout_ms: int = 5000
    read_timeout_ms: int = 3000
    reconnect_attempts: int = 2
    retry_delay_ms: int = 250
    simulation_profile: str = "normal"


def _has_controls(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


def validate_endpoint(source: str, *, allow_private_network: bool = False) -> str:
    """Validate a numeric camera endpoint without DNS or a network request.

    Literal addresses prevent DNS rebinding. LAN addresses require explicit
    administrator opt-in. Loopback, link-local (including metadata services),
    unspecified, multicast, reserved endpoints and non-stream ports are denied.
    Credentials and tokens belong in the secret store, not in persisted URLs.
    """
    if not isinstance(source, str) or len(source) > 1024 or _has_controls(source):
        raise ValueError("Enter a camera stream URL of at most 1024 characters.")
    source = source.strip()
    try:
        parts = urlsplit(source)
        if (
            parts.scheme not in ("rtsp", "http", "https")
            or not parts.hostname
            or "%" in parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.query
            or parts.fragment
            or _has_controls(unquote(parts.path))
            or "\\" in source
        ):
            raise ValueError
        host = ipaddress.ip_address(parts.hostname)
        port = (
            parts.port
            if parts.port is not None
            else {"rtsp": 554, "http": 80, "https": 443}[parts.scheme]
        )
    except ValueError, TypeError:
        raise ValueError(
            "Use an RTSP/HTTP/HTTPS stream with a numeric camera IP address; "
            "do not include login details, query tokens or fragments."
        ) from None
    if isinstance(host, ipaddress.IPv6Address) and host.ipv4_mapped is not None:
        raise ValueError("IPv4-mapped IPv6 camera addresses are not supported.")
    if (
        host.is_loopback
        or host.is_link_local
        or host.is_unspecified
        or host.is_multicast
        or host.is_reserved
    ):
        raise ValueError("This address is not an allowed camera endpoint.")
    lan = any(
        host.version == network.version and host in network for network in _LAN_NETWORKS
    )
    if lan and not allow_private_network:
        raise ValueError(
            "An administrator must authorize this specific LAN camera before connecting."
        )
    if not lan and not host.is_global:
        raise ValueError("This address is not an allowed camera endpoint.")
    if port not in STREAM_PORTS:
        raise ValueError(
            "Use an allowed camera streaming port (80, 81, 443, 554, 8000, 8080, 8081, 8554 or 8888)."
        )
    netloc = "[" + str(host) + "]" if host.version == 6 else str(host)
    if parts.port is not None:
        netloc += ":" + str(port)
    return urlunsplit((parts.scheme, netloc, parts.path or "/", "", ""))


def validate_config(config: CameraConfig) -> CameraConfig:
    if not isinstance(config, CameraConfig):
        raise ValueError("Camera configuration is required.")  # noqa: TRY004 - public validation contract
    for value, limit in ((config.device_id, 64), (config.name, 100)):
        if (
            not isinstance(value, str)
            or not value.strip()
            or len(value) > limit
            or _has_controls(value)
        ):
            raise ValueError("Enter a valid device identifier and name.")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", config.device_id):
        raise ValueError(
            "Use letters, numbers, hyphens or underscores in the device identifier."
        )
    if config.device_type not in DEVICE_TYPES:
        raise ValueError("Select a supported camera type.")
    for setting, lower, upper in (
        (config.open_timeout_ms, 250, 15000),
        (config.read_timeout_ms, 250, 10000),
        (config.reconnect_attempts, 0, 5),
        (config.retry_delay_ms, 0, 2000),
    ):
        if (
            isinstance(setting, bool)
            or not isinstance(setting, int)
            or not lower <= setting <= upper
        ):
            raise ValueError(
                "Camera timeouts/retry limits are outside the supported range."
            )
    if not isinstance(config.allow_private_network, bool):
        raise ValueError("LAN authorization must be explicitly enabled or disabled.")  # noqa: TRY004 - public validation contract
    source = str(config.source).strip()
    if config.device_type in ("builtin", "usb"):
        if not source.isdecimal() or not 0 <= int(source) <= 31:
            raise ValueError("Select a local camera index between 0 and 31.")
        source = str(int(source))
    elif config.device_type == "mock":
        if config.simulation_profile not in SIMULATION_PROFILES:
            raise ValueError("Select a supported simulation profile.")
        if (
            not re.fullmatch(r"mock://[a-zA-Z0-9_-]+", source)
            or len(source) > 100
            or _has_controls(source)
        ):
            raise ValueError("A simulated camera source must start with mock://.")
    else:
        source = validate_endpoint(
            source, allow_private_network=config.allow_private_network
        )
        scheme = urlsplit(source).scheme
        if config.device_type == "rtsp" and scheme != "rtsp":
            raise ValueError("An RTSP device requires an rtsp:// stream URL.")
        if config.device_type in ("http", "esp32") and scheme not in ("http", "https"):
            raise ValueError("This device requires an HTTP/HTTPS MJPEG stream URL.")
    return replace(
        config,
        source=source,
        name=config.name.strip(),
        device_id=config.device_id.strip(),
    )


def valid_frame(frame: Any) -> bool:
    return (
        isinstance(frame, np.ndarray)
        and frame.dtype == np.uint8
        and frame.ndim == 3
        and frame.shape[2] == 3
        and 16 <= frame.shape[0] <= 8192
        and 16 <= frame.shape[1] <= 8192
        and frame.shape[0] * frame.shape[1] <= 20_000_000
    )


class HTTPMJPEGCapture:
    """Bounded HTTP JPEG/MJPEG capture with header authentication, no redirects.

    Passwords are passed to requests authentication in memory; they are never
    embedded in the URL or included in raised messages. HTTPS verifies normal
    certificate trust. Insecure/self-signed certificate bypass is not provided.
    """

    def __init__(self, config: CameraConfig, credentials: dict[str, str] | None = None):
        import requests

        self._session = requests.Session()
        self._session.trust_env = (
            False  # Do not route a campus camera through environment proxies.
        )
        self._response = None
        self._chunks: Any = None
        self._buffer = bytearray()
        self._timeout = config.read_timeout_ms / 1000
        self.error = "Camera stream could not be opened."
        auth = None
        if credentials:
            username = credentials.get("username", "")
            password = credentials.get("password", "")
            mode = credentials.get("mode", "basic")
            if (
                not username
                or not password
                or len(username) > 256
                or len(password) > 1024
                or _has_controls(username)
                or _has_controls(password)
                or mode not in ("basic", "digest")
            ):
                self.release()
                raise ValueError(
                    "Enter valid camera credentials and Basic or Digest authentication."
                )
            auth = (
                requests.auth.HTTPDigestAuth(username, password)
                if mode == "digest"
                else requests.auth.HTTPBasicAuth(username, password)
            )
        try:
            self._response = self._session.get(
                config.source,
                auth=auth,
                stream=True,
                allow_redirects=False,
                verify=True,
                timeout=(config.open_timeout_ms / 1000, self._timeout),
            )
            if self._response.status_code in (401, 403):
                self.error = (
                    "Camera authentication was rejected. Check the saved device login."
                )
                self.release()
                return
            media = (
                self._response.headers.get("Content-Type", "")
                .split(";", 1)[0]
                .strip()
                .lower()
            )
            if self._response.status_code != 200 or media not in (
                "multipart/x-mixed-replace",
                "image/jpeg",
            ):
                self.error = "The endpoint must return JPEG/MJPEG directly; redirects and web login pages are not supported."
                self.release()
                return
            self._chunks = iter(self._response.iter_content(chunk_size=4096))
            self.error = ""
        except requests.RequestException:
            self.error = "HTTP camera connection failed or timed out. Check address, certificate and network access."
            self.release()

    def isOpened(self):
        return self._response is not None and self._chunks is not None

    def read(self):
        if not self.isOpened():
            return False, None
        deadline = time.monotonic() + self._timeout
        try:
            while time.monotonic() < deadline:
                start = self._buffer.find(b"\xff\xd8")
                end = self._buffer.find(b"\xff\xd9", max(0, start + 2))
                if start >= 0 and end >= 0:
                    raw = bytes(self._buffer[start : end + 2])
                    del self._buffer[: end + 2]
                    from PIL import Image

                    with Image.open(io.BytesIO(raw)) as image:
                        width, height = image.size
                        if (
                            width * height > 20_000_000
                            or not 16 <= width <= 8192
                            or not 16 <= height <= 8192
                        ):
                            self.error = "Camera JPEG dimensions exceed the supported frame limit."
                            break
                    frame = cv2.imdecode(
                        np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR
                    )
                    if valid_frame(frame):
                        return True, frame
                    self.error = "Camera returned a corrupt or unsupported JPEG frame."
                    break
                self._buffer.extend(next(self._chunks))
                if len(self._buffer) > 2 * 1024 * 1024:
                    self.error = "Camera frame exceeds the supported 2 MiB compressed-frame limit."
                    break
            else:
                self.error = (
                    "Camera did not deliver a complete frame before the read deadline."
                )
        except Exception:  # noqa: BLE001 - untrusted decoder/transport boundary, redact exception values
            # Requests/driver errors may include a URL or authentication context.
            self.error = "HTTP camera stream was interrupted or timed out."
        self.release()
        return False, None

    def release(self):
        if self._response is not None:
            self._response.close()
        self._response = None
        self._chunks = None
        self._buffer.clear()
        self._session.close()


class CameraAdapter:
    def __init__(self, config: CameraConfig, *, credentials=None, capture_factory=None):
        self.config = validate_config(config)
        self._credentials = credentials
        self._capture_factory = capture_factory
        self._capture: Any = None
        self._state = "disconnected"
        self._last_error = ""
        self._last_connected: str | None = None
        self._resolution: tuple[int, int] | None = None
        self._frame_times: list[float] = []
        self._attempt = 0

    def _open_capture(self):
        factory = self._capture_factory or cv2.VideoCapture
        if self.config.device_type in ("builtin", "usb"):
            return factory(
                int(self.config.source),
                cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY,
            )
        if self._credentials:
            raise ValueError(
                "Authenticated RTSP streams require an authorized protected gateway. Do not put camera passwords in URLs."
            )
        return factory(
            self.config.source,
            cv2.CAP_FFMPEG,
            [
                cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,
                self.config.open_timeout_ms,
                cv2.CAP_PROP_READ_TIMEOUT_MSEC,
                self.config.read_timeout_ms,
            ],
        )

    def connect(self) -> bool:
        self.disconnect()
        self._state = "connecting"
        if self._credentials and urlsplit(self.config.source).scheme == "rtsp":
            self._fail(
                "Authenticated RTSP requires an authorized protected stream gateway; do not put camera passwords in URLs."
            )
            return False
        try:
            self._capture = self._open_capture()
            if self._capture is None or not self._capture.isOpened():
                error = getattr(self._capture, "error", "")
                self._fail(
                    error
                    or "Camera unavailable or already in use. Check connection and Windows camera permissions."
                )
                return False
            self._state = "connected"
            self._last_error = ""
            self._last_connected = datetime.now(UTC).isoformat()
            self._frame_times.clear()
            return True
        except Exception:  # noqa: BLE001 - native capture boundary; exceptions can echo credentials
            # Deliberately omit exception values: native libraries may echo secrets.
            self._fail(
                "Camera connection failed. Check its configuration, supported stream format and access permissions."
            )
            return False

    def _fail(self, message):
        self._close_capture()
        self._state = "error"
        self._last_error = message

    def _close_capture(self):
        capture, self._capture = self._capture, None
        if capture is not None:
            try:
                capture.release()
            except Exception:  # noqa: BLE001 - keep shutdown safe even when a native driver fails
                self._last_error = "Camera driver could not confirm resource release."

    def disconnect(self):
        self._close_capture()
        self._state = "disconnected"

    def is_connected(self) -> bool:
        return self._state == "connected" and self._capture is not None

    def read_frame(self):
        if not self.is_connected():
            return False, None
        try:
            ok, frame = self._capture.read()
            if not ok or not valid_frame(frame):
                error = getattr(self._capture, "error", "")
                self._fail(
                    error or "Camera stream interrupted or returned an invalid frame."
                )
                return False, None
            self._resolution = (int(frame.shape[1]), int(frame.shape[0]))
            self._frame_times.append(time.monotonic())
            self._frame_times = self._frame_times[-30:]
            return True, frame
        except Exception:  # noqa: BLE001 - native frame decoder boundary
            self._fail("Camera stream interrupted or timed out.")
            return False, None

    def reconnect(self, cancel_event: threading.Event | None = None) -> bool:
        self.disconnect()
        stop = cancel_event or threading.Event()
        for attempt in range(self.config.reconnect_attempts):
            if stop.is_set():
                self._state = "disconnected"
                return False
            self._attempt = attempt + 1
            if self.connect():
                return True
            if attempt + 1 < self.config.reconnect_attempts and stop.wait(
                self.config.retry_delay_ms / 1000
            ):
                self._state = "disconnected"
                return False
        self._state = "error"
        self._last_error = (
            self._last_error
            or "Reconnect limit reached. Use Reconnect after checking the device."
        )
        return False

    def get_device_info(self) -> dict[str, Any]:
        fps = None
        frame_times = tuple(self._frame_times)
        if len(frame_times) >= 2:
            elapsed = frame_times[-1] - frame_times[0]
            if elapsed > 0:
                fps = round((len(frame_times) - 1) / elapsed, 1)
        return {
            "device_id": self.config.device_id,
            "name": self.config.name,
            "device_type": self.config.device_type,
            "protocol": "simulation"
            if self.config.device_type == "mock"
            else (
                "local"
                if self.config.device_type in ("builtin", "usb")
                else urlsplit(self.config.source).scheme
            ),
            "resolution": self._resolution,
            "fps": fps,
            "simulated": self.config.device_type == "mock",
        }

    def get_connection_status(self) -> dict[str, Any]:
        return {
            "state": self._state,
            "last_error": self._last_error,
            "last_connected": self._last_connected,
            "reconnect_attempt": self._attempt,
        }

    # OpenCV compatibility keeps the attendance decision pipeline device-independent.
    def isOpened(self):
        return self.is_connected()

    def read(self):
        return self.read_frame()

    def release(self):
        self.disconnect()
        self._credentials = None


class LocalCameraAdapter(CameraAdapter):
    pass


class USBCameraAdapter(LocalCameraAdapter):
    pass


class RTSPCameraAdapter(CameraAdapter):
    pass


class HTTPStreamAdapter(CameraAdapter):
    def _open_capture(self):
        if self._capture_factory:
            return self._capture_factory(self.config.source)
        return HTTPMJPEGCapture(self.config, self._credentials)


class RaspberryPiStreamAdapter(HTTPStreamAdapter):
    def _open_capture(self):
        if urlsplit(self.config.source).scheme in ("http", "https"):
            return super()._open_capture()
        return CameraAdapter._open_capture(self)


class ESP32CAMStreamAdapter(HTTPStreamAdapter):
    pass


class MockCameraAdapter(CameraAdapter):
    """Clearly synthetic shapes; recognition tests inject permitted feature vectors.

    No real or generated photograph of a person is used. Failures occur once,
    so a bounded reconnect can recover without an endless simulated fault loop.
    """

    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)
        self._frame_index = 0
        self._injected: str | None = None
        self._profile_faulted = False

    def inject_failure(self, failure="disconnect"):
        if failure not in ("disconnect", "corrupt", "connect"):
            raise ValueError(
                "Select disconnect, corrupt or connect simulation failure."
            )
        self._injected = failure

    def connect(self):
        self.disconnect()
        if (
            self.config.simulation_profile == "connect_failure"
            or self._injected == "connect"
        ):
            self._injected = None
            self._state = "error"
            self._last_error = "SIMULATED connection failure."
            return False
        self._state = "connected"
        self._last_error = ""
        self._last_connected = datetime.now(UTC).isoformat()
        self._frame_times.clear()
        return True

    def is_connected(self):
        return self._state == "connected"

    def read_frame(self):
        if not self.is_connected():
            return False, None
        self._frame_index += 1
        failure = self._injected
        if failure != "connect":
            self._injected = None
        if (
            not self._profile_faulted
            and self._frame_index == 4
            and self.config.simulation_profile in ("interruption", "corrupt")
        ):
            self._profile_faulted = True
            failure = self.config.simulation_profile
        if failure in ("disconnect", "interruption", "corrupt"):
            self._state = "error"
            self._last_error = "SIMULATED " + failure + "."
            return False, None
        if self.config.simulation_profile == "low_fps":
            time.sleep(0.15)
        frame = np.full((480, 640, 3), (24, 18, 12), dtype=np.uint8)
        for index in range(4):
            x = 70 + index * 155
            cv2.rectangle(
                frame, (x - 30, 175), (x + 30, 265), (70 + index * 30, 125, 180), -1
            )
            cv2.putText(
                frame,
                str(index + 1),
                (x - 10, 230),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 255, 255),
                2,
            )
        cv2.putText(
            frame,
            "SIMULATED CAMERA - NO REAL FACES",
            (25, 45),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (220, 235, 255),
            1,
        )
        cv2.putText(
            frame,
            "Frame " + str(self._frame_index),
            (25, 435),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (180, 195, 215),
            1,
        )
        self._resolution = (640, 480)
        self._frame_times.append(time.monotonic())
        self._frame_times = self._frame_times[-30:]
        return True, frame


def create_adapter(
    config: CameraConfig, *, credentials=None, capture_factory=None
) -> CameraAdapter:
    config = validate_config(config)
    adapter = {
        "builtin": LocalCameraAdapter,
        "usb": USBCameraAdapter,
        "rtsp": RTSPCameraAdapter,
        "http": HTTPStreamAdapter,
        "raspberry_pi": RaspberryPiStreamAdapter,
        "esp32": ESP32CAMStreamAdapter,
        "mock": MockCameraAdapter,
    }[config.device_type]
    return adapter(config, credentials=credentials, capture_factory=capture_factory)


def discover_simulated_devices() -> list[CameraConfig]:
    return [
        CameraConfig("mock-" + kind, "SIMULATED " + title, "mock", "mock://" + kind)
        for kind, title in (
            ("usb", "USB camera"),
            ("ip", "IP camera"),
            ("raspberry-pi", "Raspberry Pi stream"),
        )
    ]


def discover_devices(
    max_devices: int = 4, *, capture_factory=None, cancel_event=None
) -> list[CameraConfig]:
    """Explicit local-index probe only; never scans the LAN or reads saved devices.

    Device names/USB identities are not guessed from index numbers. Probing a
    local driver can block despite cancellation; run this in a worker. Windows
    drivers do not uniformly implement OpenCV network timeout properties.
    """
    if (
        isinstance(max_devices, bool)
        or not isinstance(max_devices, int)
        or not 0 <= max_devices <= 16
    ):
        raise ValueError("Scan between 0 and 16 local camera indices.")
    devices = []
    for index in range(max_devices):
        if cancel_event is not None and cancel_event.is_set():
            break
        config = CameraConfig(
            "local-" + str(index), "Local camera " + str(index), "builtin", str(index)
        )
        adapter = LocalCameraAdapter(config, capture_factory=capture_factory)
        try:
            if adapter.connect():
                ok, _ = adapter.read_frame()
                if ok:
                    devices.append(config)
        finally:
            adapter.release()
    return devices
