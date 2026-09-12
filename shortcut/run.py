#!/usr/bin/env python3
"""Start Short Cut.

    python run.py                 # start the server, print the URL
    python run.py --demo          # same, with invented incidents so you can see it work
    python run.py --port 8000     # pick the port yourself

Open the printed URL on your phone (same wifi) and add it to your home screen.
"""
from __future__ import annotations

import os
import socket
import sys


def _free_port(preferred: int = 8750) -> int:
    """Use `preferred` if it's free, otherwise let the OS choose."""
    with socket.socket() as s:
        try:
            s.bind(("0.0.0.0", preferred))
            return preferred
        except OSError:
            pass
    with socket.socket() as s:
        s.bind(("0.0.0.0", 0))
        return s.getsockname()[1]


def _lan_ip() -> str:
    """Best guess at this machine's address on the local network."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("8.8.8.8", 80))  # no traffic sent; just resolves the route
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def main() -> None:
    if "--demo" in sys.argv:
        os.environ["SHORTCUT_DEMO"] = "1"

    port = _free_port()
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])

    ip = _lan_ip()
    print(f"\n  Short Cut on this computer:  http://127.0.0.1:{port}")
    print(f"  Short Cut on your phone:     http://{ip}:{port}")
    if os.environ.get("SHORTCUT_DEMO"):
        print("\n  DEMO MODE - the incidents you see are invented, not real.")
    if not os.environ.get("GOOGLE_MAPS_API_KEY"):
        print("\n  No GOOGLE_MAPS_API_KEY set - no drive times. Everything else works.")
    print("\n  Phone location needs HTTPS unless the address is localhost.")
    print("  See the README under 'Getting location to work on your phone'.\n")

    import uvicorn

    uvicorn.run("shortcut.server:app", host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
