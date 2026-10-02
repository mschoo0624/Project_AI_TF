"""
Start the web UI.

    python main.py                 # http://127.0.0.1:8000 opens in the browser
    python main.py --port 8080 --no-browser
"""
from __future__ import annotations

import argparse
import threading
import webbrowser

import uvicorn


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    if not args.no_browser:
        url = f"http://127.0.0.1:{args.port}"
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    uvicorn.run("legalrag.server:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
