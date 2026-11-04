"""Verify a QR student's claimed identity against their local enrolled face."""

import io
import threading
import time
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

from .face import FaceEngine


class CameraBusy(RuntimeError):
    pass


@dataclass(frozen=True)
class FaceResult:
    status: str
    box: tuple[float, float, float, float] | None = None


def normalized_box(face, frame):
    height, width = frame.shape[:2]
    x, y, w, h = (float(v) for v in face[:4])
    left, top = max(0, min(1, x / width)), max(0, min(1, y / height))
    right, bottom = (
        max(left, min(1, (x + w) / width)),
        max(top, min(1, (y + h) / height)),
    )
    return left, top, right - left, bottom - top


def decode_frame(raw):
    try:
        with Image.open(io.BytesIO(raw), formats=("JPEG",)) as photo:
            width, height = photo.size
            if not 160 <= width <= 800 or not 160 <= height <= 800:
                raise ValueError("Invalid camera frame size.")
            return cv2.cvtColor(np.asarray(photo.convert("RGB")), cv2.COLOR_RGB2BGR)
    except OSError, ValueError, Image.DecompressionBombError, cv2.error:
        raise ValueError("The camera frame could not be read. Try again.") from None


def face_pose(face):
    eyes = sorted((np.asarray(face[4:6]), np.asarray(face[6:8])), key=lambda p: p[0])
    axis = eyes[1] - eyes[0]
    width_squared = float(axis @ axis)
    if width_squared < 24**2 or abs(float(axis[1])) > 0.35 * abs(float(axis[0])):
        return None
    nose = np.asarray(face[8:10])
    offset = float((nose - (eyes[0] + eyes[1]) / 2) @ axis) / width_squared
    if abs(offset) <= 0.13:
        return "center"
    # The phone preview is mirrored. The raw frame sent to the server is not.
    if 0.17 <= offset <= 0.65:
        return "left"
    if -0.65 <= offset <= -0.17:
        return "right"
    return None


class QRFaceVerifier:
    def __init__(self, threshold):
        self.threshold = threshold
        self.lock = threading.Lock()
        self.engine = FaceEngine()

    def verify(self, raw, student, expected_pose):
        frame = decode_frame(raw)
        if not self.lock.acquire(timeout=1.0):
            raise CameraBusy()
        try:
            now = time.monotonic()
            cached = student.get("_qr_reference")
            if not cached or now >= cached[0]:
                refs, _ = self.engine.load_references([student])
                if not refs:
                    return FaceResult("enrollment")
                cached = student["_qr_reference"] = (now + 8, refs[0][1])
            faces = self.engine.detect(frame)
            if len(faces) != 1:
                return FaceResult("one_face")
            face = faces[0]
            if not np.isfinite(face).all():
                return FaceResult("one_face")
            box = normalized_box(face, frame)
            if min(face[2:4]) < 78:
                return FaceResult("closer", box)
            feature = self.engine.encode(frame, face)
            norm = np.linalg.norm(feature)
            if feature.shape != (128,) or not np.isfinite(feature).all() or norm < 1e-9:
                return FaceResult("closer", box)
            score = float(np.clip(cached[1] @ (feature / norm), -1, 1))
            if score < self.threshold:
                return FaceResult("mismatch", box)
            return FaceResult(
                "match" if face_pose(face) == expected_pose else "pose", box
            )
        finally:
            self.lock.release()
