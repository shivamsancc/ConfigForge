"""
ConfigFoundry server entry point.

Usage
-----
::

    python3 server.py
    python3 server.py --db /path/to/shared/configforge.db --port 8420
    python3 server.py --config /etc/configfoundry/config.yaml --port 8420

The ``--config`` flag accepts a YAML file that can specify any
``AppConfig`` field (provider, connection URL, pool size, etc.).
When both ``--config`` and ``--db`` are provided, ``--db`` overrides
the ``sqlite_path`` inside the config file.

Defaults are chosen so a first-time user can just run ``python3 server.py``
with zero flags and get something working immediately.
"""
import argparse
import os
import sys
import threading
import time
import webbrowser

import uvicorn

from app import create_app
from core.logging import configure_logging
from core.storage.config import AppConfig, DatabaseConfig


def parse_args():
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db")
    p = argparse.ArgumentParser(
        description="ConfigFoundry — shared SNMP collector config YAML generator",
    )
    p.add_argument(
        "--db",
        default=None,
        help=(
            "Path to the SQLite database file.  "
            "Overrides the sqlite_path in --config if both are supplied.  "
            f"Default (when no --config): {os.path.join(here, 'configforge.db')}"
        ),
    )
    p.add_argument(
        "--config",
        default=None,
        metavar="YAML_FILE",
        help=(
            "Path to a YAML configuration file.  "
            "Enables non-SQLite backends and advanced options.  "
            "See docs/storage-architecture.md for the full schema."
        ),
    )
    p.add_argument("--port", type=int, default=8420,
                   help="Port to listen on (default: 8420)")
    p.add_argument(
        "--host", default="0.0.0.0",
        help="Host/interface to bind (default: 0.0.0.0)",
    )
    p.add_argument("--no-browser", action="store_true",
                   help="Don't automatically open a browser tab on startup")
    return p.parse_args()


def build_config(args) -> AppConfig:
    """
    Assemble an ``AppConfig`` from CLI arguments.

    Priority:
    1. ``--config`` YAML file (if supplied)
    2. ``--db`` flag overrides ``sqlite_path`` in the YAML
    3. Defaults (SQLite, ``db/configforge.db``)
    """
    if args.config:
        cfg = AppConfig.from_yaml(args.config)
        if args.db:
            cfg.database.sqlite_path = args.db
    elif args.db:
        cfg = AppConfig.for_sqlite(args.db)
    else:
        here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db")
        cfg = AppConfig.for_sqlite(os.path.join(here, "configforge.db"))

    return cfg


def open_browser_when_ready(url: str, host: str, port: int):
    """Poll until the server is accepting connections, then open a tab."""
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
        pass


def main():
    args = parse_args()
    config = build_config(args)

    # Configure logging FIRST — before create_app() so that startup log
    # messages emitted from the lifespan handler are already captured.
    configure_logging(config.logging)

    display_host = "localhost" if args.host == "0.0.0.0" else args.host
    url = f"http://{display_host}:{args.port}/"

    print("=" * 60)
    print(f"  ConfigFoundry is running")
    print(f"  Provider: {config.database.provider}")
    print(f"  Local:    http://localhost:{args.port}/")
    if args.host == "0.0.0.0":
        print(f"  Network:  http://<this machine's IP>:{args.port}/")
    if config.database.provider == "sqlite":
        print(f"  Database: {config.database.sqlite_path}")
    elif config.database.connection_url:
        # Mask password in output
        import re
        safe_url = re.sub(r":[^:@]+@", ":***@", config.database.connection_url)
        print(f"  Database: {safe_url}")
    print("=" * 60)
    print("  Press Ctrl+C to stop.")
    print()

    if not args.no_browser:
        threading.Thread(
            target=open_browser_when_ready,
            args=(url, args.host, args.port),
            daemon=True,
        ).start()

    app = create_app(config=config)

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
