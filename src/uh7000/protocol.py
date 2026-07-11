"""Verified, read-only portions of the UH-7000 vendor protocol.

Write requests discovered in the legacy research are intentionally absent from
this production module.  A request is promoted here only after isolated capture,
readback and recovery tests establish its semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

VID = 0x0644
PID = 0x8048
REQUEST_TYPE_VENDOR_IN = 0xC0
REQUEST_SELECTOR_STATUS = 0x49
REQUEST_STATE_PAGE = 0x55
STATE_PAGE_SIZE = 512
VERIFIED_STATE_PAGES = (0x1F00, 0x007C, 0x007D, 0x007E, 0x007F)


class ControlTransport(Protocol):
    def control_read(
        self,
        request: int,
        value: int,
        index: int,
        length: int,
        timeout_ms: int = 1000,
    ) -> bytes: ...


@dataclass(frozen=True, slots=True)
class StatePage:
    index: int
    payload: bytes

    def __post_init__(self) -> None:
        if len(self.payload) != STATE_PAGE_SIZE:
            raise ValueError(f"state page must be {STATE_PAGE_SIZE} bytes")

    @property
    def is_all_ff(self) -> bool:
        return all(byte == 0xFF for byte in self.payload)

    @property
    def is_all_zero(self) -> bool:
        return not any(self.payload)


def read_selector_status(transport: ControlTransport) -> int:
    payload = transport.control_read(REQUEST_SELECTOR_STATUS, 0, 0, 1)
    if len(payload) != 1:
        raise IOError(f"selector status returned {len(payload)} bytes, expected 1")
    return payload[0]


def read_state_page(transport: ControlTransport, index: int) -> StatePage:
    if index not in VERIFIED_STATE_PAGES:
        raise ValueError(f"state page 0x{index:04x} is not in the verified read-only set")
    payload = transport.control_read(REQUEST_STATE_PAGE, 0, index, STATE_PAGE_SIZE)
    return StatePage(index=index, payload=payload)


def parse_firmware_hint(page: StatePage) -> str | None:
    """Return a conservative printable firmware hint, never a guessed version."""
    for marker in (b"UH-7000", b"UH7000", b"VER", b"Version"):
        position = page.payload.find(marker)
        if position < 0:
            continue
        candidate = page.payload[position : position + 48]
        text = "".join(chr(byte) if 32 <= byte < 127 else " " for byte in candidate)
        text = " ".join(text.split())
        if text:
            return text
    return None


class MemoryTransport:
    """Deterministic transport used by tests and offline protocol fixtures."""

    def __init__(self, responses: dict[tuple[int, int, int, int], bytes]):
        self.responses = responses
        self.requests: list[tuple[int, int, int, int, int]] = []

    def control_read(
        self,
        request: int,
        value: int,
        index: int,
        length: int,
        timeout_ms: int = 1000,
    ) -> bytes:
        self.requests.append((request, value, index, length, timeout_ms))
        key = (request, value, index, length)
        if key not in self.responses:
            raise IOError(f"no fixture for request {key!r}")
        return self.responses[key]
