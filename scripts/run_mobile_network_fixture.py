"""Serve a tiny deterministic HTTP target for mobile weak-network testing."""

from __future__ import annotations

import argparse
import json
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse


class FixtureHandler(BaseHTTPRequestHandler):
    """Return a stable catalog item and record every request."""

    server_version = "QaMobileNetworkFixture/1.0"
    delay_seconds = 0.0

    def do_GET(self) -> None:
        self._respond()

    def do_POST(self) -> None:
        self._respond()

    def _respond(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health/live":
            self._write_json(HTTPStatus.OK, {"status": "ok"})
            return
        if parsed.path.startswith("/api/v1/e2e/sessions/"):
            time.sleep(self.delay_seconds)
            self._write_json(
                HTTPStatus.OK,
                {
                    "id": 1001,
                    "name": "week30-network-fixture",
                    "status": "active",
                },
            )
            return
        self._write_json(
            HTTPStatus.NOT_FOUND,
            {"error": "not found", "path": parsed.path},
        )

    def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        print(
            json.dumps(
                {
                    "method": self.command,
                    "path": self.path,
                    "status": status.value,
                },
                separators=(",", ":"),
            ),
            flush=True,
        )

    def log_message(self, format: str, *args: object) -> None:
        del format, args


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--delay-ms", type=int, default=0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 1 <= args.port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    if args.delay_ms < 0:
        raise ValueError("delay-ms must not be negative")

    FixtureHandler.delay_seconds = args.delay_ms / 1000
    server = ThreadingHTTPServer((args.host, args.port), FixtureHandler)
    print(
        json.dumps(
            {
                "status": "listening",
                "host": args.host,
                "port": args.port,
                "delay_ms": args.delay_ms,
            },
            separators=(",", ":"),
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
