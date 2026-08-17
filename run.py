#!/usr/bin/env python3
"""Development launcher.

    python run.py            # open the desktop app window (pywebview)
    python run.py --web      # just run the server and print the URL (browser)
"""
import sys


def main() -> None:
    if "--web" in sys.argv:
        import uvicorn

        from app.main import _free_port
        port = _free_port()
        print(f"ForTheMix running at http://127.0.0.1:{port}")
        uvicorn.run("app.server:app", host="127.0.0.1", port=port, log_level="info")
    else:
        from app.main import main as app_main

        app_main()


if __name__ == "__main__":
    main()
