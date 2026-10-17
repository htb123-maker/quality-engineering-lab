"""Small typed client for the Toxiproxy control API."""

from __future__ import annotations

from typing import Literal, Self
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ConfigDict, Field

ToxicStream = Literal["downstream", "upstream"]


class ToxiproxyProxy(BaseModel):
    """One proxy known to the Toxiproxy server."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    name: str = Field(min_length=1)
    listen: str = Field(min_length=1)
    upstream: str = Field(min_length=1)
    enabled: bool = True


class Toxic(BaseModel):
    """One latency, timeout, reset, or bandwidth fault."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    type: str = Field(min_length=1)
    stream: ToxicStream = "downstream"
    toxicity: float = Field(default=1.0, ge=0.0, le=1.0)
    attributes: dict[str, int | float | str] = Field(default_factory=dict)


class ToxiproxyClient:
    """Manage proxies without binding tests to Toxiproxy internals."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 2.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            transport=transport,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the control API connection."""

        self._client.close()

    def list_proxies(self) -> dict[str, ToxiproxyProxy]:
        """Return every configured proxy keyed by name."""

        response = self._client.get("/proxies")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Toxiproxy /proxies must return an object")
        return {
            name: ToxiproxyProxy.model_validate(value)
            for name, value in payload.items()
            if isinstance(name, str) and isinstance(value, dict)
        }

    def ensure_proxy(
        self,
        *,
        name: str,
        listen: str,
        upstream: str,
    ) -> ToxiproxyProxy:
        """Create a proxy, replacing a stale one with the same name."""

        existing = self.list_proxies().get(name)
        if existing is not None:
            if (
                existing.listen == listen
                and existing.upstream == upstream
                and existing.enabled
            ):
                return existing
            self.delete_proxy(name)

        response = self._client.post(
            "/proxies",
            json={"name": name, "listen": listen, "upstream": upstream},
        )
        response.raise_for_status()
        return ToxiproxyProxy.model_validate(response.json())

    def delete_proxy(self, name: str) -> None:
        """Delete one proxy; a missing proxy is already in the desired state."""

        response = self._client.delete(f"/proxies/{quote(name, safe='')}")
        if response.status_code != 404:
            response.raise_for_status()

    def set_proxy_enabled(self, name: str, *, enabled: bool) -> ToxiproxyProxy:
        """Open or close a proxy without changing its upstream."""

        response = self._client.patch(
            f"/proxies/{quote(name, safe='')}",
            json={"enabled": enabled},
        )
        response.raise_for_status()
        return ToxiproxyProxy.model_validate(response.json())

    def add_toxic(self, proxy_name: str, toxic: Toxic) -> Toxic:
        """Attach one toxic to a proxy."""

        response = self._client.post(
            f"/proxies/{quote(proxy_name, safe='')}/toxics",
            json=toxic.model_dump(mode="json"),
        )
        response.raise_for_status()
        return Toxic.model_validate(response.json())

    def remove_toxic(self, proxy_name: str, toxic_name: str) -> None:
        """Remove one toxic; a missing toxic is already cleared."""

        response = self._client.delete(
            f"/proxies/{quote(proxy_name, safe='')}/toxics/"
            f"{quote(toxic_name, safe='')}"
        )
        if response.status_code != 404:
            response.raise_for_status()

    def reset(self) -> None:
        """Delete every proxy owned by the current fault-injection run."""

        for name in self.list_proxies():
            self.delete_proxy(name)


def latency_toxic(
    *,
    latency_ms: int,
    name: str = "latency",
    jitter_ms: int = 0,
) -> Toxic:
    """Build a deterministic response latency fault."""

    return Toxic(
        name=name,
        type="latency",
        attributes={"latency": latency_ms, "jitter": jitter_ms},
    )


def reset_peer_toxic(*, name: str = "reset-peer") -> Toxic:
    """Build a fault that closes established connections."""

    return Toxic(name=name, type="reset_peer", attributes={})


def timeout_toxic(
    *,
    timeout_ms: int,
    name: str = "timeout",
) -> Toxic:
    """Build a fault that stops proxying packets for a bounded interval."""

    return Toxic(
        name=name,
        type="timeout",
        attributes={"timeout": timeout_ms},
    )
