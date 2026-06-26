"""
ConfigForge server entry point.

Usage:
    python3 server.py
    python3 server.py --db /path/to/shared/configforge.db --port 8420

Defaults are chosen so a first-time user can just run `python3 server.py`
with zero flags and get something working immediately: a local db file
next to this script, port 8420, and the browser opens automatically.
"""
import argparse
import os
import sys
import threading
import time
import webbrowser
from http.server import ThreadingHTTPServer

import storage
import handler


def parse_args():
    here = os.path.dirname(os.path.abspath(__file__))
    p = argparse.ArgumentParser(
        description="ConfigForge -- shared SNMP collector config YAML generator",
    )
    p.add_argument("--db", default=os.path.join(here, "configforge.db"),
                    help="Path to the SQLite database file (default: configforge.db next to this script). "
                         "Point this at a shared network drive so a whole team shares one dataset.")
    p.add_argument("--port", type=int, default=8420, help="Port to listen on (default: 8420)")
    p.add_argument("--host", default="0.0.0.0",
                    help="Host/interface to bind (default: 0.0.0.0, i.e. reachable from other machines on the network)")
    p.add_argument("--no-browser", action="store_true",
                    help="Don't automatically open a browser tab on startup")
    return p.parse_args()


def open_browser_when_ready(url: str, host: str, port: int):
    """Poll the server with a plain socket connect until it accepts
    connections, then open the browser. Avoids a race where the browser
    opens before the HTTP server is actually listening."""
    import socket
    deadline = time.time() + 10
    probe_host = "127.0.0.1" if host == "0.0.0.0" else host
    while time.time() < deadline:
        try:
            with socket.create_connection((probe_host, port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.1)
    try:
        webbrowser.open(url)
    except Exception:
        pass  # headless environment or no browser available -- not fatal


def main():
    args = parse_args()

    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
    handler.STATIC_DIR = static_dir

    storage.init(args.db)

    server = ThreadingHTTPServer((args.host, args.port), handler.Handler)

    display_host = "localhost" if args.host == "0.0.0.0" else args.host
    url = f"http://{display_host}:{args.port}/"

    print("=" * 60)
    print("  ConfigForge is running")
    print(f"  Local:    http://localhost:{args.port}/")
    if args.host == "0.0.0.0":
        print(f"  Network:  http://<this machine's IP>:{args.port}/  (reachable from other devices)")
    print(f"  Database: {args.db}")
    print("=" * 60)
    print("  Press Ctrl+C to stop the server.")
    print()

    if not args.no_browser:
        threading.Thread(target=open_browser_when_ready, args=(url, args.host, args.port), daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()
        sys.exit(0)


if __name__ == "__main__":
    main()
