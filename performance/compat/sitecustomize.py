"""Windows-only Locust import shim for blocked geventhttpclient binaries."""

from __future__ import annotations

import os
import sys
from types import ModuleType

if os.name == "nt" and os.getenv("QA_PERF_STUB_FASTHTTP") == "1":
    geventhttpclient = ModuleType("geventhttpclient")
    geventhttpclient.__path__ = []
    useragent = ModuleType("geventhttpclient.useragent")

    class ConnectionError(OSError):
        """Stand-in exception used by Locust's HttpUser implementation."""

    useragent.ConnectionError = ConnectionError  # type: ignore[attr-defined]
    geventhttpclient.useragent = useragent  # type: ignore[attr-defined]
    sys.modules["geventhttpclient"] = geventhttpclient
    sys.modules["geventhttpclient.useragent"] = useragent

    fasthttp = ModuleType("locust.contrib.fasthttp")

    class FastHttpUser:
        """Unused placeholder; Windows journeys fall back to HttpUser."""

    fasthttp.FastHttpUser = FastHttpUser  # type: ignore[attr-defined]
    sys.modules["locust.contrib.fasthttp"] = fasthttp
