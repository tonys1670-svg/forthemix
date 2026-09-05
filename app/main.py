"""Desktop entry point: run the FastAPI server in-process and open the UI.

Preferred: a native pywebview window. If that can't start (e.g. the Windows
WebView2 runtime is missing, or a headless environment), it does NOT fail
silently — it automatically opens the app in the user's default web browser and
keeps the local server running. Every startup stage is written to a log file so
a "nothing happened" launch can be diagnosed.
"""
from __future__ import annotations

import socket
import threading
import time
import traceback
import webbrowser
from contextlib import closing

import uvicorn

from . import APP_NAME
from .server import app

_LOG = None


def _log(msg: str) -> None:
    """Best-effort append to %APPDATA%/ForTheMix/startup.log and stdout."""
    global _LOG
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        print(line, flush=True)
    except Exception:
        pass
    try:
        if _LOG is None:
            from . import config
            _LOG = str(config.DATA_DIR / "startup.log")
        with open(_LOG, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_until_up(host: str, port: int, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            if s.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.1)
    return False


def run_server(host: str, port: int) -> None:
    try:
        uvicorn.run(app, host=host, port=port, log_level="warning")
    except Exception:
        _log("Server thread crashed:\n" + traceback.format_exc())


def _setup_bundled_binaries() -> None:
    """Put bundled CLI tools (RubberBand) on PATH so pyrubberband can find them."""
    import os

    from . import config
    for sub in ("rubberband", ""):
        d = str(config.resource_path(sub)) if sub else str(config.resource_path())
        if os.path.isdir(d):
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")


def _open_in_browser_and_wait(url: str) -> None:
    _log(f"Opening the app in your default browser: {url}")
    try:
        webbrowser.open(url)
    except Exception:
        _log("Could not launch a browser automatically. Open this address yourself: " + url)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


def main() -> None:
    try:
        _log(f"Starting {APP_NAME} …")
        _setup_bundled_binaries()
        host, port = "127.0.0.1", _free_port()
        threading.Thread(target=run_server, args=(host, port), daemon=True).start()

        url = f"http://{host}:{port}"
        if not _wait_until_up(host, port):
            _log("The local server did not start in time.")
            _open_in_browser_and_wait(url)
            return
        _log(f"Server is up at {url}")

        # Preferred: a native window via pywebview.
        try:
            import webview
            _log("Creating the app window (pywebview)…")
            webview.create_window(APP_NAME, url, width=1280, height=820, min_size=(1024, 680))
            webview.start()
            _log("Window closed — exiting.")
            return
        except Exception:
            _log("Native window unavailable, falling back to the browser:\n" + traceback.format_exc())
            _open_in_browser_and_wait(url)
    except Exception:
        _log("Fatal error on startup:\n" + traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
