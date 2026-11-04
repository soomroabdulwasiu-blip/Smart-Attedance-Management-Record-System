"""Run legacy scenarios in subprocesses against disposable Oracle schemas only."""

import argparse
import json
import os
import re
import runpy
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

SAFE = (
    "dashboard_oracle_integration.py",
    "lifecycle_oracle_integration.py",
    "manual_preservation_integration.py",
    "oracle_integration.py",
    "request_workflows_integration.py",
    "session_roster_integration.py",
    "signup_ui_integration.py",
)
PRIVATE_FIXTURES = (
    "admin_new_integration.py",
    "admin_ui_integration.py",
    "camera_completion_integration.py",
    "face_oracle_integration.py",
    "group_integration.py",
    "known_unknown_integration.py",
)
ROOT = Path(__file__).resolve().parents[1]


def run_suite(env, report_path, names=SAFE, include_private=True):
    results = []
    for name in names:
        if name not in SAFE:
            raise ValueError("Scenario outside the non-biometric allowlist.")
        with tempfile.TemporaryDirectory(prefix="amrs-legacy-") as temporary:
            work = Path(temporary)
            (work / "work").mkdir()
            child_env = dict(env, PYTHONPATH=str(ROOT), AMRS_REDUCE_MOTION="1")
            child_env.pop("AMRS_QR_CERT_FILE", None)
            child_env.pop("AMRS_QR_KEY_FILE", None)
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "tools.legacy_test_check", "--case", name],
                    cwd=work,
                    env=child_env,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=100,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                results.append(
                    {
                        "test": name,
                        "status": "failed",
                        "detail": "Timed out after 100 seconds",
                    }
                )
                print("Legacy " + name + ": failed (timeout)", flush=True)
                continue
            status = "passed" if result.returncode == 0 else "failed"
            # Never print captured logs: exceptions can include synthetic tokens or passwords.
            detail = ""
            if result.returncode:
                codes = re.findall(r"ORA-\d+", result.stdout + result.stderr)
                detail = (
                    ", ".join(sorted(set(codes)))
                    or "Scenario assertion or runtime error"
                )
                for line in result.stdout.splitlines():
                    if line.startswith("SAFE_DIAGNOSTIC "):
                        detail = json.loads(line[len("SAFE_DIAGNOSTIC ") :])
            results.append({"test": name, "status": status, "detail": detail})
            print("Legacy " + name + ": " + status, flush=True)
    for name in PRIVATE_FIXTURES if include_private else ():
        results.append(
            {
                "test": name,
                "status": "not_run",
                "detail": "Requires existing private face photographs and/or model fixtures; protected biometric files were not accessed. Not a Docker dependency.",
            }
        )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results


def execute_case(name):
    if name not in SAFE:
        raise ValueError("Scenario not in the non-biometric allowlist.")
    user = os.environ.get("AMRS_DB_USERNAME", "")
    schema = os.environ.get("AMRS_DB_SCHEMA", "")
    if (
        not re.fullmatch(r"AMRST_R_[A-F0-9]{10}", user)
        or not re.fullmatch(r"AMRST_M_[A-F0-9]{10}", schema)
        or user[8:] != schema[8:]
    ):
        raise RuntimeError("Disposable runtime/owner accounts required.")
    import oracledb

    original = oracledb.connect

    def connect(*args, **kwargs):
        # Historical scripts hard-code AMRS. Redirect only this subprocess to its test user.
        if args or kwargs.get("user") != "AMRS":
            raise RuntimeError("Unexpected legacy connection refused.")
        connection = original(
            user=user,
            password=os.environ["AMRS_DB_PASSWORD"],
            dsn=os.environ["AMRS_ORACLE_DSN"],
        )
        connection.cursor().execute("ALTER SESSION SET CURRENT_SCHEMA=" + schema)
        return connection

    oracledb.connect = connect
    from amrs import face, qr, settings

    private = Path.cwd() / "isolated-data"
    private.mkdir()
    face.FACE_DIR = private / "faces"
    face.LEGACY_FACE_DIR = private / "legacy-faces"
    settings.SETTINGS_PATH = private / "ui_settings.json"
    # Any unexpected reference to Path.home goes into the empty test sandbox.
    Path.home = classmethod(lambda cls: private)  # type: ignore[method-assign, assignment]
    address = qr.public_address
    qr.public_address = lambda value=None: address(value or "127.0.0.1")
    constructor = qr.ExclusiveQRServer.__init__

    def local_server(self, host, *args, **kwargs):
        return constructor(self, "127.0.0.1", *args, **kwargs)

    qr.ExclusiveQRServer.__init__ = local_server  # type: ignore[method-assign]
    try:
        runpy.run_path(str(ROOT / "tests" / name), run_name="__main__")
    except Exception as exc:
        # Exception values and local variables can contain credentials/tokens.
        frames = traceback.extract_tb(exc.__traceback__)
        diagnostic = (
            type(exc).__name__
            + ": "
            + ", ".join(
                Path(frame.filename).name + ":" + str(frame.lineno) for frame in frames
            )
        )
        if name == "dashboard_oracle_integration.py" and isinstance(
            exc, AssertionError
        ):
            trace = exc.__traceback__
            assert trace is not None
            while trace.tb_next is not None:
                trace = trace.tb_next
            state = trace.tb_frame.f_locals
            index = state.get("i")
            if isinstance(index, int):
                diagnostic += "; page_index=" + str(index)
                window = state.get("sw") or state.get("tw")
                if window is not None:
                    page = window.tabs.widget(index)
                    diagnostic += "; overflow=" + str(
                        page.horizontalScrollBar().maximum()
                    )
                    diagnostic += "; viewport=" + str(page.viewport().width())
                    from PySide6.QtWidgets import QWidget

                    diagnostic += "; widest=" + ",".join(
                        type(widget).__name__
                        + ":"
                        + str(widget.minimumSizeHint().width())
                        for widget in page.findChildren(QWidget)
                        if widget.minimumSizeHint().width()
                        > page.viewport().width() - 64
                    )
        print("SAFE_DIAGNOSTIC " + json.dumps(diagnostic), flush=True)
        raise
    finally:
        import shiboken6
        from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if isinstance(app, QApplication):
            if not QThreadPool.globalInstance().waitForDone(5000):
                raise RuntimeError("Legacy background task did not finish")
            for widget in app.topLevelWidgets():
                widget.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            shiboken6.delete(app)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=SAFE)
    execute_case(parser.parse_args().case)


if __name__ == "__main__":
    main()
