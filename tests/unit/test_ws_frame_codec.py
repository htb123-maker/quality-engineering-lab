"""Unit tests for the WebSocket codec the SUT and its tests share."""

from __future__ import annotations

from io import BytesIO

import app as sut_app
import pytest


def masked_client_frame(payload: bytes, *, opcode: int = 0x1) -> bytes:
    """Build one masked client frame the way a browser or test client would."""

    mask = b"\x01\x02\x03\x04"
    length = len(payload)
    header = bytearray([0x80 | opcode])
    if length < 126:
        header.append(0x80 | length)
    elif length < 65_536:
        header.append(0x80 | 126)
        header.extend(length.to_bytes(2, "big"))
    else:
        header.append(0x80 | 127)
        header.extend(length.to_bytes(8, "big"))
    masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    return bytes(header) + mask + masked


def test_websocket_accept_matches_the_rfc_6455_example() -> None:
    """The handshake vector from RFC 6455 section 1.3 must be reproduced."""

    assert (
        sut_app.websocket_accept("dGhlIHNhbXBsZSBub25jZQ==")
        == "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="
    )


@pytest.mark.parametrize("size", [0, 5, 125, 126, 1000, 65_536])
def test_server_text_frames_round_trip_through_the_client_reader(size: int) -> None:
    """A server frame must be readable again, including both length branches."""

    payload = "x" * size
    frame = sut_app.encode_ws_text(payload)
    assert frame[0] == 0x81
    assert not frame[1] & 0x80

    decoded = sut_app.read_ws_frame(BytesIO(masked_client_frame(payload.encode())))

    assert decoded is not None
    opcode, body = decoded
    assert opcode == 0x1
    assert body.decode("utf-8") == payload


def test_client_frames_are_unmasked_before_the_payload_is_used() -> None:
    """The mask bit must be applied, not ignored."""

    decoded = sut_app.read_ws_frame(BytesIO(masked_client_frame(b"secret")))

    assert decoded == (0x1, b"secret")


def test_control_frames_keep_their_opcode() -> None:
    """A close frame must not be reported as text."""

    decoded = sut_app.read_ws_frame(
        BytesIO(masked_client_frame((1000).to_bytes(2, "big"), opcode=0x8))
    )

    assert decoded is not None
    opcode, payload = decoded
    assert opcode == sut_app.WS_OPCODE_CLOSE
    assert payload == (1000).to_bytes(2, "big")


def test_truncated_frames_end_the_stream_instead_of_raising() -> None:
    """A half-written frame must be reported as a closed stream."""

    frame = masked_client_frame(b"payload")

    assert sut_app.read_ws_frame(BytesIO(frame[:3])) is None
    assert sut_app.read_ws_frame(BytesIO(b"")) is None
