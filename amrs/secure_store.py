"""Windows-user encrypted local secrets; never stores plaintext credentials."""

import base64
import json
import os
import threading
import uuid
from pathlib import Path

from .mail_delivery import _crypt
from .paths import profile_root

_lock = threading.RLock()


class SecretStore:
    def __init__(self, namespace="camera", directory=None):
        if namespace not in ("camera", "database"):
            raise ValueError("Unknown credential namespace.")
        directory = Path(directory) if directory else profile_root()
        self.path = directory / (namespace + "-vault.json")

    def _load(self):
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return json.loads(
                _crypt(
                    base64.b64decode(payload["encrypted"], validate=True), True
                ).decode()
            )
        except ValueError, KeyError, TypeError, OSError:
            raise ValueError(
                "The encrypted credential store cannot be opened by this Windows user. Configure it again."
            ) from None

    def get(self, key):
        with _lock:
            return self._load().get(key)

    def set(self, key, value):
        if not key or len(key) > 80:
            raise ValueError("Invalid credential reference.")
        with _lock:
            data = self._load()
            if value is None:
                data.pop(key, None)
            else:
                data[key] = value
            encrypted = _crypt(json.dumps(data).encode())
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_name(
                self.path.name + "." + uuid.uuid4().hex + ".tmp"
            )
            try:
                temporary.write_text(
                    json.dumps({"encrypted": base64.b64encode(encrypted).decode()}),
                    encoding="utf-8",
                )
                os.replace(temporary, self.path)
            finally:
                temporary.unlink(missing_ok=True)
