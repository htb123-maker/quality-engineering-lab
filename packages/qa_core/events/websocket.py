"""Minimal RFC 6455 client used to verify pushed SUT events.

The SUT hand-rolls its WebSocket endpoint, so the test side speaks the same
wire protocol directly: a handshake, masked client frames, and a text frame per
event. Keeping the client small makes the failure messages readable when a
stream stalls, and no browser or extra dependency is needed to test push
delivery.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Self
from urllib.parse import urlsplit

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
OPCODE_TEXT = 0x1
OPCODE_CLOSE = 0x8
OPCODE_PING = 0x9
OPCODE_PONG = 0xA
DEFAULT_TIMEOUT_SECONDS = 5.0


class WebSocketError(RuntimeError):
    """Base class for WebSocket client failures."""


class WebSocketTimeout(TimeoutError):
    """Raised when no expected frame arrives before the deadline."""

    def __init__(self, description: str, timeout: float) -> None:
        super().__init__(f"{description} did not arrive within {timeout:.2f}s")
        self.description = description
        self.timeout = timeout


class WebSocketClosed(WebSocketError):
    """Raised when the peer closed the stream."""

    def __init__(self, code: int | None, reason: str) -> None:
        detail = f"WebSocket closed by peer (code={code}, reason={reason!r})"
        super().__init__(detail)
        self.code = code
        self.reason = reason


class WebSocketHandshakeError(WebSocketError):
    """Raised when the upgrade is rejected, carrying the HTTP response."""

    def __init__(
        self,
        status_code: int,
        headers: Mapping[str, str],
        body: bytes,
    ) -> None:
        super().__init__(f"WebSocket handshake rejected with HTTP {status_code}")
        self.status_code = status_code
        self.headers = dict(headers)
        self.body = body

    @property
    def payload(self) -> dict[str, Any]:
        """Return the JSON error body, or an empty dict when it is not JSON."""

        try:
            decoded: Any = json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return decoded if isinstance(decoded, dict) else {}


def websocket_accept(key: str) -> str:
    """Return the expected Sec-WebSocket-Accept value for a client key."""

    digest = hashlib.sha1((key + WS_GUID).encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


def events_url(api_base_url: str, workspace_slug: str) -> str:
    """Return the WebSocket URL of one workspace event stream."""

    parts = urlsplit(api_base_url)
    scheme = {"http": "ws", "https": "wss"}.get(parts.scheme)
    if scheme is None:
        raise ValueError(f"unsupported API base URL scheme: {parts.scheme!r}")
    return f"{scheme}://{parts.netloc}/api/v1/workspaces/{workspace_slug}/events"


@dataclass(frozen=True)
class WebSocketEvent:
    """One pushed event frame."""

    type: str
    workspace: str
    sequence: int
    occurred_at: float
    data: dict[str, Any]

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> Self:
        """Validate and copy one decoded frame payload."""

        raw_data = payload.get("data")
        return cls(
            type=str(payload["type"]),
            workspace=str(payload["workspace"]),
            sequence=int(payload["sequence"]),
            occurred_at=float(payload["occurred_at"]),
            data=raw_data if isinstance(raw_data, dict) else {},
        )

    @classmethod
    def from_json(cls, raw: str) -> Self:
        """Parse one text frame into an event."""

        payload: Any = json.loads(raw)
        if not isinstance(payload, dict):
            raise WebSocketError("event frame must be a JSON object")
        return cls.from_payload(payload)


class _SocketBuffer:
    """Read exact byte counts and header lines from a blocking socket."""

    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock
        self._buffer = bytearray()

    def set_timeout(self, timeout: float | None) -> None:
        """Apply a socket timeout for the next read."""

        self._sock.settimeout(timeout)

    def read_exactly(self, length: int) -> bytes:
        """Return exactly ``length`` bytes, or raise when the peer closes."""

        while len(self._buffer) < length:
            try:
                chunk = self._sock.recv(max(4096, length - len(self._buffer)))
            except TimeoutError as exc:
                raise WebSocketTimeout("frame", float(self._sock.gettimeout() or 0)) from exc
            if not chunk:
                raise WebSocketClosed(None, "peer closed the stream")
            self._buffer.extend(chunk)
        data = bytes(self._buffer[:length])
        del self._buffer[:length]
        return data

    def read_line(self) -> str:
        """Return one CRLF-terminated line without the terminator."""

        while b"\r\n" not in self._buffer:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise WebSocketClosed(None, "peer closed during handshake")
            self._buffer.extend(chunk)
        index = self._buffer.index(b"\r\n")
        line = bytes(self._buffer[:index])
        del self._buffer[: index + 2]
        return line.decode("latin-1")


class WebSocketConnection:
    """One upgraded connection to the SUT event stream."""

    def __init__(self, sock: socket.socket, reader: _SocketBuffer) -> None:
        self._sock = sock
        self._reader = reader
        self._closed = False

    @classmethod
    def connect(
        cls,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> Self:
        """Open a connection and perform the client handshake."""

        parts = urlsplit(url)
        if parts.scheme not in {"ws", "wss"}:
            raise ValueError(f"unsupported WebSocket scheme: {parts.scheme!r}")
        if parts.scheme == "wss":
            raise WebSocketError("the local SUT event stream is plain ws://")

        host = parts.hostname or "127.0.0.1"
        port = parts.port or 80
        target = parts.path or "/"
        if parts.query:
            target = f"{target}?{parts.query}"
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request_lines = [
            f"GET {target} HTTP/1.1",
            f"Host: {parts.netloc}",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Key: {key}",
            "Sec-WebSocket-Version: 13",
        ]
        for name, value in (headers or {}).items():
            request_lines.append(f"{name}: {value}")
        request = ("\r\n".join(request_lines) + "\r\n\r\n").encode("utf-8")

        sock = socket.create_connection((host, port), timeout=timeout)
        sock.settimeout(timeout)
        try:
            sock.sendall(request)
            reader = _SocketBuffer(sock)
            status_code = _status_code(reader.read_line())
            response_headers = _read_headers(reader)
            if status_code != 101:
                raise WebSocketHandshakeError(
                    status_code,
                    response_headers,
                    _read_body(reader, response_headers),
                )
            accept = response_headers.get("sec-websocket-accept", "")
            if accept != websocket_accept(key):
                raise WebSocketError(
                    "Sec-WebSocket-Accept did not match the client key"
                )
        except BaseException:
            sock.close()
            raise
        return cls(sock, reader)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def receive_event(self, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> WebSocketEvent:
        """Return the next event, answering control frames on the way."""

        return WebSocketEvent.from_json(self.receive_text(timeout=timeout))

    def receive_event_of_type(
        self,
        event_types: Sequence[str],
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> WebSocketEvent:
        """Return the next event whose type is wanted, skipping the others."""

        wanted = set(event_types)
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise WebSocketTimeout(f"any of {sorted(wanted)}", timeout)
            event = self.receive_event(timeout=remaining)
            if event.type in wanted:
                return event

    def receive_text(self, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> str:
        """Return the payload of the next text frame."""

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise WebSocketTimeout("text frame", timeout)
            opcode, payload = self._receive_frame(timeout=remaining)
            if opcode == OPCODE_TEXT:
                return payload.decode("utf-8")
            if opcode == OPCODE_PING:
                self._send_frame(OPCODE_PONG, payload)
                continue
            if opcode == OPCODE_PONG:
                continue
            if opcode == OPCODE_CLOSE:
                self._closed = True
                code, reason = _close_details(payload)
                raise WebSocketClosed(code, reason)
            raise WebSocketError(f"unsupported frame opcode: {opcode}")

    def send_text(self, text: str) -> None:
        """Send one masked text frame."""

        self._send_frame(OPCODE_TEXT, text.encode("utf-8"))

    def close(self) -> None:
        """Send a close frame when possible and release the socket."""

        if not self._closed:
            try:
                self._send_frame(OPCODE_CLOSE, (1000).to_bytes(2, "big"))
            except OSError:
                pass
        self._closed = True
        self._sock.close()

    def _receive_frame(self, *, timeout: float) -> tuple[int, bytes]:
        """Return the next frame, rejecting frames the SUT never sends."""

        self._reader.set_timeout(timeout)
        header = self._reader.read_exactly(2)
        final = bool(header[0] & 0x80)
        opcode = header[0] & 0x0F
        masked = bool(header[1] & 0x80)
        length = header[1] & 0x7F
        if length == 126:
            length = int.from_bytes(self._reader.read_exactly(2), "big")
        elif length == 127:
            length = int.from_bytes(self._reader.read_exactly(8), "big")
        if masked:
            raise WebSocketError("server-to-client frames must not be masked")
        if not final:
            raise WebSocketError("fragmented frames are not supported")
        payload = self._reader.read_exactly(length) if length else b""
        return opcode, payload

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        """Send one masked client frame."""

        header = bytearray([0x80 | opcode])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65_536:
            header.append(0x80 | 126)
            header.extend(length.to_bytes(2, "big"))
        else:
            header.append(0x80 | 127)
            header.extend(length.to_bytes(8, "big"))
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self._sock.sendall(bytes(header) + mask + masked)


def _status_code(status_line: str) -> int:
    """Extract the numeric status code from an HTTP status line."""

    parts = status_line.split(" ")
    if len(parts) < 2 or not parts[1].isdigit():
        raise WebSocketError(f"unexpected status line: {status_line!r}")
    return int(parts[1])


def _read_headers(reader: _SocketBuffer) -> dict[str, str]:
    """Read response headers into a lowercase-keyed mapping."""

    headers: dict[str, str] = {}
    while True:
        line = reader.read_line()
        if not line:
            return headers
        name, separator, value = line.partition(":")
        if not separator:
            raise WebSocketError(f"malformed header line: {line!r}")
        headers[name.strip().lower()] = value.strip()


def _read_body(reader: _SocketBuffer, headers: Mapping[str, str]) -> bytes:
    """Read the response body of a rejected handshake."""

    raw_length = headers.get("content-length")
    if raw_length is None:
        return b""
    try:
        length = int(raw_length)
    except ValueError:
        return b""
    return reader.read_exactly(length) if length > 0 else b""


def _close_details(payload: bytes) -> tuple[int | None, str]:
    """Return the close code and reason carried by a close frame."""

    if len(payload) < 2:
        return None, ""
    code = int.from_bytes(payload[:2], "big")
    return code, payload[2:].decode("utf-8", errors="replace")
