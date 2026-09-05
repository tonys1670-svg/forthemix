"""Desktop entry point: run the FastAPI server in-process and open a native window.

Uses pywebview so the packaged Windows app opens as a real application window
rather than a browser tab. Falls back to printing the local URL if no GUI
backend is available (e.g. headless).
"""
from __future__ import annotations

import socket
import threading
import time
from contextlib import closing

import uvicorn

from . import APP_NAME
from .server import app


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_until_up(host: str, port: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            if s.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.1)
    return False


def run_server(host: str, port: int) -> None:
    uvicorn.run(app, host=host, port=port, log_level="warning")


def _setup_bundled_binaries() -> None:
    """Put bundled CLI tools (RubberBand) on PATH so pyrubberband can find them."""
    import os

    from . import config
    for sub in ("rubberband", ""):
        d = str(config.resource_path(sub)) if sub else str(config.resource_path())
        if os.path.isdir(d):
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")


def main() -> None:
    _setup_bundled_binaries()
    host, port = "127.0.0.1", _free_port()
    server_thread = threading.Thread(target=run_server, args=(host, port), daemon=True)
    server_thread.start()

    url = f"http://{host}:{port}"
    if not _wait_until_up(host, port):
        print(f"Server did not start in time. Try opening {url} manually.")
        return

    try:
        import webview

        webview.create_window(APP_NAME, url, width=1280, height=820, min_size=(1024, 680))
        webview.start()
    except Exception as exc:
        print(f"[{APP_NAME}] GUI window unavailable ({exc}).")
        print(f"[{APP_NAME}] Open this address in your browser: {url}")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
