# Hardware and camera integration

AMRS uses the same face-attendance decisions for all supported sources. `amrs/cameras.py` supplies adapters; a background worker captures frames, then the existing face engine performs detection, recognition, course eligibility checks and Oracle writes. An adapter alone never marks attendance. A successful device preview establishes frame delivery, not recognition accuracy.

## Implemented source types

| Device type | Adapter | Connection method | Verification status |
| --- | --- | --- | --- |
| Built-in laptop camera | LocalCameraAdapter | Windows DirectShow camera index | Adapter tested with injected capture; existing laptop workflow preserved; physical acceptance still required |
| Compatible external USB webcam | USBCameraAdapter | Windows camera driver and numeric index | Simulated capture/discovery verified; no external webcam available |
| RTSP IP camera | RTSPCameraAdapter | Numeric IP, allowed streaming port, OpenCV FFmpeg | Capture contract/timeouts/recovery tested with injected transport; no physical RTSP camera tested |
| HTTP/HTTPS IP camera | HTTPStreamAdapter | Direct JPEG/MJPEG endpoint, requests transport | Fragmented JPEG decoding, authentication, TLS options, redirects, failures and resource cleanup tested with synthetic transport |
| Raspberry Pi camera | RaspberryPiStreamAdapter | Existing RTSP or HTTP/HTTPS JPEG/MJPEG streaming service | Adapter selection and transport contracts tested; no direct Pi driver/GPIO access implemented |
| ESP32-CAM | ESP32CAMStreamAdapter | Compatible HTTP/HTTPS JPEG/MJPEG firmware endpoint | Protocol adapter verified with injected transport; firmware/board compatibility needs physical testing |
| Simulation | MockCameraAdapter | In-memory synthetic shapes | Deterministic connection, switching, interruption, corrupt-frame rejection and recovery tests passed |

Only supported video protocols are accepted. USB enrollment depends on the Windows driver; AMRS does not install drivers. An HDMI camera requires a compatible capture device/driver. Raspberry Pi and ESP32 adapters receive network video; they do not configure boards or flash firmware. Universal hardware compatibility is not claimed.

## Shared interface and worker ownership

`CameraConfig` contains device ID/name/type, a non-secret source, explicit LAN authorization, open/read timeouts, reconnect-attempt limit, retry delay and a simulation profile. `validate_config` rejects invalid ranges before a connection. `create_adapter(config, credentials=...)` constructs a disconnected adapter.

The worker calls `connect`, `read_frame`, `reconnect(cancel_event)` and `release`. OpenCV-compatible `isOpened`, `read` and `release` let the existing attendance pipeline use an adapter. Status contains a state, safe last error, last successful connection time and reconnect attempt. Device information contains only the user-supplied identifier/name/type, protocol, observed frame resolution and measured frame delivery rate. Manufacturer, serial number and advertised frame rate are not invented. An unknown resolution or rate remains empty until measured.

One worker owns an adapter and its capture resource. Never call synchronous connect/read/discovery from a Qt button handler. The worker passes copied frames to the UI through queued signals; it does not retain footage. Release runs in the worker's `finally` path. On switching devices, stop the previous worker and release its adapter before opening the next source.

The utility `discover_devices(max_devices=4)` explicitly probes local indices, reads one valid frame and releases every probe. It never scans the LAN. The scan result describes an index as “Local camera”; an index does not prove USB versus built-in provenance. Users choose the correct type/name. Cancellation is checked between probes. Camera enumeration may light the camera indicator.

## Windows built-in/USB setup

1. Connect the webcam using its manufacturer-supported Windows driver. Close applications that have exclusive access to the camera.
2. In Windows camera privacy settings, allow camera access for desktop applications. Check the Camera app first if no application can open it.
3. In the AMRS hardware setup workflow, explicitly scan local camera indices, or enter the known index (`0`, `1`, etc.; supported range 0–31). Preview the correct device before saving its descriptive name.
4. Select the saved/enabled source for an authorized class attendance session. A camera test preview does not mark attendance.
5. Stop capture before unplugging or changing the active source. Test disconnection and recovery before a pilot session.

Windows DirectShow drivers do not uniformly honor network-style timeout properties. Local driver open/read/release calls can still block inside a native driver. Background execution protects the UI, but a process-isolated capture service would be required to enforce a hard deadline on a defective driver. AMRS does not forcibly terminate capture threads or claim that every driver can be interrupted instantly.

## IP camera validation and credentials

Use the camera's direct numeric IP streaming address, for example `rtsp://192.168.1.25:8554/classroom` or `http://192.168.1.25:81/stream`. A LAN source requires the administrator to authorize that specific configured endpoint. Hostnames are intentionally refused to avoid DNS rebinding and unbounded resolver behavior. Supported ports are 80, 81, 443, 554, 8000, 8080, 8081, 8554 and 8888; a different device port requires a reviewed code/configuration-policy change.

Loopback, link-local/cloud metadata, unspecified, multicast, reserved/non-global non-LAN addresses, IPv4-mapped IPv6 addresses and non-streaming ports are rejected. URL userinfo, query tokens, fragments, controls and encoded line breaks are rejected before connection. A camera URL must not contain passwords or access tokens. Store the separate camera login through the application secret mechanism, never in Oracle device JSON or diagnostic messages.

HTTP/HTTPS JPEG/MJPEG authentication accepts separately supplied Basic or Digest credentials. Requests uses header authentication, verified HTTPS certificates, no environment proxy and no redirects. A redirect, login webpage, unsupported content type or 401/403 response fails safely. Configure a direct streaming URL. For HTTPS with an IP literal, the certificate must be trusted and valid for that IP; disabling certificate verification is not supported. Basic authentication over plain HTTP is visible to the network, so prefer HTTPS or an appropriately secured camera network.

Authenticated RTSP credentials are deliberately not embedded into native FFmpeg URLs: native diagnostics can echo those URLs. Use a protected, authorized gateway that handles camera authentication outside AMRS and exposes a permitted non-credential stream on a restricted camera network. If that deployment is unavailable, authenticated RTSP is an explicit limitation rather than a claimed working feature. Plain authorized RTSP remains supported through FFmpeg.

Endpoint validation is not a network firewall. In particular, a compromised RTSP source may influence its native backend's redirect/substream behavior. Isolate camera networks, restrict egress to the approved device/gateway, restrict device administration and review campus routing before deployment. AMRS does not automatically discover or contact arbitrary internal services.

## Raspberry Pi streaming procedure

On a separately managed Raspberry Pi, install a supported Raspberry Pi OS/camera combination and first verify the camera using the Pi's documented tools. Current Raspberry Pi documentation describes `rpicam-*` applications and RTSP streaming servers. AMRS runs on Windows and does not install software or change the Pi automatically. [Raspberry Pi camera software documentation](https://www.raspberrypi.com/documentation/accessories/camera-software.html).

An administrator may configure MediaMTX on the Pi with a camera path, for example the documented `paths: cam: source: rpiCamera` configuration. The resulting direct RTSP endpoint commonly has the form `rtsp://<PI-IP>:8554/cam`. Enter the Pi's actual numeric IP and configured port/path as a Raspberry Pi device in AMRS; explicitly authorize the LAN endpoint, test connectivity, preview and select it for attendance. Do not paste browser/WebRTC pages into the stream URL. Match the actual stream configuration instead of assuming a path or codec. Authentication and network isolation must be configured by the Pi administrator. [Raspberry Pi RTSP streaming instructions](https://www.raspberrypi.com/documentation/accessories/camera-software.html).

This connection is a network streaming adapter. Pi camera driver support, stream startup, codec decoding, latency and resolution remain physical acceptance items. No direct CSI-camera, GPIO, remote device administration or firmware upload implementation is claimed.

## ESP32-CAM procedure and limits

Espressif supplies camera components and a CameraWebServer firmware example. Use firmware for the exact board/sensor, verify the device's direct JPEG/MJPEG stream independently, then configure its numeric HTTP endpoint in AMRS (often a separate streaming port such as 81). Board power, Wi-Fi, firmware authentication and camera sensor compatibility belong to the device deployment. [Espressif CameraWebServer example](https://github.com/espressif/arduino-esp32/tree/master/libraries/ESP32/examples/Camera/CameraWebServer), [Espressif camera component](https://github.com/espressif/esp32-camera).

Some firmware provides only snapshots, limited frame rates or an unauthenticated stream. Camera boards with low resolution or unstable Wi-Fi may be unsuitable for multiple distant faces. No ESP32 firmware was flashed and no board was available for this verification. ESP32-CAM is not represented as validated for classroom recognition.

## Timeouts, reconnection and diagnostics

Network defaults are a 5-second open timeout and 3-second read timeout, with two reconnect attempts and 250 ms between attempts. Configuration bounds are 250–15000 ms for open, 250–10000 ms for read, 0–5 reconnect attempts and 0–2000 ms retry delay. Cancellation is checked between retries and during retry waits. A native call already in progress can last until its backend/driver returns. OpenCV's open/read timeout parameters apply to FFmpeg/GStreamer, not universally to all backends. [OpenCV video I/O properties](https://docs.opencv.org/5.0/main_modules/videoio_flags_base.html).

HTTP buffering holds at most 2 MiB of compressed frame data and checks JPEG dimensions before decoding. Frames must be 8-bit BGR arrays, at least 16 pixels in both dimensions, at most 8192 pixels in either dimension and at most 20 million pixels overall. Invalid/corrupt frames are not sent to recognition. The preview displays current frames; adapters do not save videos.

If connection fails, check power, correct index/IP/port/path, Windows access, another application using the webcam, stream format, certificate trust and saved authentication. For interruption, verify physical/network connectivity before reconnecting. Reconnection is bounded; repeated failure requires a user action after fixing the cause. Driver and HTTP exception values are not copied into status because they may contain sensitive context.

## Simulation mode

`discover_simulated_devices` returns three clearly named SIMULATED configurations representing USB, IP and Raspberry Pi source choices. They all use the mock adapter; they do not contact those physical devices or certify their protocols. The synthetic frames contain colored numbered blocks and a SIMULATED CAMERA label, not human photographs or production faces.

Profiles are `normal`, `interruption`, `corrupt`, `connect_failure` and `low_fps`. Interruption/corrupt profiles produce a one-time fault after three frames, allowing bounded recovery. `inject_failure` can produce disconnect, corrupt or next-connect failure. The low-frame-rate profile adds a short bounded delay. Recognition tests must inject permitted synthetic detections/features; the mock image itself is not expected to be recognized as a real enrolled student. Oracle attendance tests use only isolated synthetic student/course fixtures.

Automated adapter tests are in `tests/test_camera_adapters.py`. They test endpoint guards, type selection, resource ownership, invalid frames, bounded/cancelled recovery, simulated switching, HTTP authentication/TLS configuration, no redirects, frame decoding, buffer limits and safe errors without accessing hardware or private biometric fixtures.

## Physical acceptance record required before deployment

For each intended camera, record the exact model/driver/firmware, actual endpoint protocol, resolution and observed frame rate. Then:

1. Obtain informed consent and authorize the test class/student roster; retain a manual alternative.
2. Verify the built-in camera first, then a USB webcam and each intended network source independently.
3. Verify one enrolled consenting person, one unknown person and a mixed group. Confirm unknown/uncertain faces never create attendance and known faces are confirmed only after Oracle commits.
4. Check left/right mirror alignment and readable boxes/labels at 950x650, 1280x720, 1366x768 and 1920x1080.
5. Repeat at measured distances, backlighting/low light, glasses, partial occlusion and the intended room positions. Report false accepts/rejects instead of assuming accuracy.
6. Test duplicate prevention, class eligibility, camera unplug/network loss, bounded reconnect, database loss/recovery, source switching and application shutdown.
7. Measure frame age, recognition/commit latency and CPU/RAM with increasing group sizes. Claim 10–20 visible-person support only after representative physical results justify it.

No live hardware verification, liveness/anti-spoofing validation, production network approval, recognition fairness assessment or university-scale performance result is established by the synthetic adapter tests.
