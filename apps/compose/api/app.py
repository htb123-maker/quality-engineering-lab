"""Small read-only API used as the local system under test."""

from __future__ import annotations

import json
import logging
import os
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

import psycopg
import redis
from psycopg.rows import dict_row

POSTGRES_DSN = os.getenv(
    "QA_POSTGRES_DSN",
    "postgresql://qa:qa@postgres:5432/qa",
)
REDIS_URL = os.getenv("QA_REDIS_URL", "redis://redis:6379/0")
LOG_LEVEL = os.getenv("QA_LOG_LEVEL", "INFO").upper()
CATALOG_PATH = re.compile(r"^/api/v1/workspaces/([^/]+)/catalog$")

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
LOGGER = logging.getLogger("sut-api")


def _postgres_check() -> dict[str, Any]:
    with psycopg.connect(POSTGRES_DSN, connect_timeout=2) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_user")
            row = cursor.fetchone()

    return {
        "status": "ok",
        "database": row[0] if row else None,
        "user": row[1] if row else None,
    }


def _redis_check() -> dict[str, Any]:
    client = redis.Redis.from_url(
        REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    try:
        pong = client.ping()
    finally:
        client.close()

    return {"status": "ok", "ping": bool(pong)}


def _catalog_payload(slug: str) -> tuple[int, dict[str, Any]]:
    with psycopg.connect(POSTGRES_DSN, connect_timeout=2) as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT id, slug, name
                FROM workspaces
                WHERE slug = %s
                """,
                (slug,),
            )
            workspace = cursor.fetchone()
            if workspace is None:
                return HTTPStatus.NOT_FOUND, {
                    "error": "workspace_not_found",
                    "message": f"Workspace '{slug}' was not found.",
                }

            cursor.execute(
                """
                SELECT id, sku, name, price_cents, status
                FROM catalog_items
                WHERE workspace_id = %s
                ORDER BY id
                """,
                (workspace["id"],),
            )
            items = cursor.fetchall()

    return HTTPStatus.OK, {
        "workspace": {
            "slug": workspace["slug"],
            "name": workspace["name"],
        },
        "items": items,
        "count": len(items),
    }


class SutRequestHandler(BaseHTTPRequestHandler):
    """Serve health and read-only catalog endpoints."""

    server_version = "QualityLabSut/0.1"

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path

        if path == "/":
            self._send_json(
                HTTPStatus.OK,
                {
                    "service": "quality-engineering-lab-sut",
                    "status": "ok",
                    "endpoints": [
                        "/health/live",
                        "/health/ready",
                        "/api/v1/workspaces/{slug}/catalog",
                    ],
                },
            )
            return

        if path == "/health/live":
            self._send_json(HTTPStatus.OK, {"status": "live"})
            return

        if path == "/health/ready":
            self._handle_readiness()
            return

        catalog_match = CATALOG_PATH.fullmatch(path)
        if catalog_match:
            self._handle_catalog(catalog_match.group(1))
            return

        self._send_json(
            HTTPStatus.NOT_FOUND,
            {
                "error": "not_found",
                "message": f"No route matches GET {path}.",
            },
        )

    def _handle_readiness(self) -> None:
        checks: dict[str, dict[str, Any]] = {}

        for name, check in (
            ("postgres", _postgres_check),
            ("redis", _redis_check),
        ):
            try:
                checks[name] = check()
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Readiness check failed for %s: %s", name, exc)
                checks[name] = {
                    "status": "error",
                    "error": type(exc).__name__,
                }

        ready = all(check["status"] == "ok" for check in checks.values())
        status = HTTPStatus.OK if ready else HTTPStatus.SERVICE_UNAVAILABLE
        self._send_json(
            status,
            {
                "status": "ready" if ready else "degraded",
                "checks": checks,
            },
        )

    def _handle_catalog(self, slug: str) -> None:
        try:
            status, payload = _catalog_payload(slug)
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Catalog query failed")
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "database_unavailable",
                    "message": type(exc).__name__,
                },
            )
            return

        self._send_json(status, payload)

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        LOGGER.info("%s - %s", self.address_string(), format % args)


def main() -> None:
    """Start the HTTP server."""

    port = int(os.getenv("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), SutRequestHandler)
    LOGGER.info("SUT API listening on port %s", port)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info("SUT API interrupted")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
