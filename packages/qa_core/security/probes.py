"""Hostile input builders used by the input-security tests.

The payloads are deliberately *text* payloads: the point is not that the SUT
filters them out, but that it stores them verbatim, never executes them, and
never lets them change the shape of the response or the schema.
"""

from __future__ import annotations

import json
from uuid import uuid4

SQL_INJECTION = "QA8'); DROP TABLE catalog_items; --"
SCRIPT_INJECTION = "<script>alert('qa')</script>"
PATH_TRAVERSAL = "../../../../etc/passwd"
NULL_BYTE = "QA8\u0000INJECT"
CRLF_INJECTION = "QA8\r\nX-Injected: 1"
UNICODE_LOOKALIKE = "QA8-\u0430\u0431\u0432-\u200b"

HOSTILE_NAMES: dict[str, str] = {
    "sql_injection": SQL_INJECTION,
    "script_injection": SCRIPT_INJECTION,
    "path_traversal": PATH_TRAVERSAL,
    "unicode_lookalike": UNICODE_LOOKALIKE,
}

CONTROL_CHARACTER_NAMES: tuple[str, ...] = (
    "line\u000afeed",
    "carriage\u000dreturn",
    CRLF_INJECTION,
    "null\u0000byte",
    "escape\u001b[31m",
    "delete\u007fchar",
)

# Slug attempts that survive URL encoding as a *single* path segment. Raw
# ``..`` segments are normalised away by HTTP clients before they reach the
# server, so those are covered by a dedicated raw-path test instead.
TRAVERSAL_SLUGS: tuple[str, ...] = (
    "..%2f..%2fetc%2fpasswd",
    "%2e%2e%2f%2e%2e%2fetc",
    "atlas%2f..%2forbit",
    "%2e%2e",
    "ATLAS",
    "atlas%20",
    "atlas%00",
    "-atlas",
    "atlas-",
)


def injection_sku() -> str:
    """Return a SKU-shaped string that carries a SQL injection attempt.

    The catalog SKU pattern only allows uppercase letters, digits, and hyphens,
    so this builder shows what the contract accepts and what it refuses.
    """

    return f"QA8-SQL-DROP-TABLE-{uuid4().hex[:6].upper()}"


def oversized_body(size_bytes: int) -> bytes:
    """Return a JSON body padded past the configured request budget."""

    padding = "x" * max(1, size_bytes)
    return json.dumps({"sku": "QA8-BIG-0001", "name": padding, "price_cents": 1}).encode()


def deeply_nested_json(depth: int) -> bytes:
    """Return a JSON document nested ``depth`` levels deep."""

    return ("[" * depth + "0" + "]" * depth).encode()


def nested_object_body(depth: int) -> bytes:
    """Return a JSON *object* whose value nests ``depth`` levels deep."""

    return (
        '{"sku": "QA8-NEST-0001", "name": '
        + "[" * depth
        + '"n"'
        + "]" * depth
        + ', "price_cents": 1}'
    ).encode()
