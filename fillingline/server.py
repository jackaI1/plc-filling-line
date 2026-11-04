"""Loopback-only training server. One owner, one scan thread, no cloud services."""
import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import signal
import time
from urllib.parse import urlsplit

from .controller import SCAN_MS
from .plant import Bench

WEB = Path(__file__).resolve().parents[1] / "web"


def handler_for(bench, host):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(1)

        def log_message(self, *_):
            pass  # No request bodies or local maintenance records in logs.

        def respond(self, data, status=200, content_type="application/json"):
            content = json.dumps(data).encode() if content_type == "application/json" else data
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(content)

        def trusted(self):
            return self.headers.get("Host") == host and self.headers.get("Origin", f"http://{host}") == f"http://{host}"

        def do_GET(self):
            if not self.trusted():
                return self.respond({"error": "Use the displayed loopback address"}, 403)
            path = urlsplit(self.path).path
            if path == "/api/state":
                return self.respond(bench.snapshot())
            routes = {"/": ("index.html", "text/html; charset=utf-8"),
                      "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                      "/style.css": ("style.css", "text/css; charset=utf-8")}
            if path not in routes:
                return self.respond({"error": "Not found"}, 404)
            filename, content_type = routes[path]
            self.respond((WEB / filename).read_bytes(), content_type=content_type)

        def do_POST(self):
            if not self.trusted():
                return self.respond({"error": "Cross-origin control rejected"}, 403)
            if self.path != "/api/command":
                return self.respond({"error": "Not found"}, 404)
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 2048 or self.headers.get("Content-Type") != "application/json":
                    raise ValueError("Send a JSON command smaller than 2049 bytes")
                bench.command(json.loads(self.rfile.read(size)))
                self.respond({"ok": True})
            except (ValueError, TypeError, UnicodeDecodeError) as exc:
                self.respond({"error": str(exc)}, 400)
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", default=".build/maintenance.sqlite3")
    args = parser.parse_args()
    bench = Bench(args.db)
    server = None
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        server = HTTPServer(("127.0.0.1", args.port), handler_for(bench, f"127.0.0.1:{args.port}"))
        server.timeout = 0.01
        print(f"Training HMI: http://127.0.0.1:{args.port}  (Ctrl+C stops)", flush=True)
        deadline = time.monotonic()
        while not stopping:
            if time.monotonic() >= deadline:
                bench.tick()
                # Delayed scans slow the simulation; never catch up in an unbounded burst.
                deadline = time.monotonic() + SCAN_MS / 1000
            server.handle_request()
    finally:
        if server:
            server.server_close()
        bench.close()


if __name__ == "__main__":
    main()
