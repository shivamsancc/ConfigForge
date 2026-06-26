#!/usr/bin/env python3
"""
SNMP Collector Config Generator -- shared server.

Run this on ONE always-on machine that everyone on the team can reach.
Everyone else just opens a browser to http://<that machine's address>:<port>/
-- no install needed on their end.

Usage:
    python3 server.py [--db PATH] [--port PORT] [--host HOST]

Defaults:
    --db    snmp_yaml_generator.db   (put this on the FSx share so it's
                                       backed up and survives the server
                                       machine being rebooted/replaced)
    --port  8420
    --host  0.0.0.0   (listen on all interfaces so teammates can reach it)

Requires nothing beyond the Python 3 standard library -- no `pip install`
needed on the machine that runs this.
"""

import argparse
import os
import sys
from http.server import ThreadingHTTPServer

import storage
from handler import Handler


def main():
    parser = argparse.ArgumentParser(description="SNMP Collector Config Generator server")
    parser.add_argument("--db", default="snmp_yaml_generator.db",
                         help="Path to the shared SQLite database file (put this on FSx)")
    parser.add_argument("--port", type=int, default=8420, help="Port to listen on")
    parser.add_argument("--host", default="0.0.0.0", help="Host/interface to bind to")
    args = parser.parse_args()

    db_path = os.path.abspath(args.db)
    print(f"Database: {db_path}")
    first_time = storage.init(db_path)
    if first_time:
        print("  (new database created)")
    else:
        print("  (existing database loaded)")

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Listening on http://{args.host}:{args.port}/")
    print("Teammates can connect by opening this machine's address in a browser, e.g.:")
    print(f"  http://<this-machine-ip-or-hostname>:{args.port}/")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()
        sys.exit(0)


if __name__ == "__main__":
    main()
