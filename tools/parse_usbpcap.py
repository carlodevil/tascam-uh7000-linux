#!/usr/bin/env python3
"""Summarize UH-7000 control transfers from classic USBPcap files."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path
from typing import Any


def control_transfers(path: Path, device: int = 1) -> list[dict[str, object]]:
    transfers: list[dict[str, object]] = []
    with path.open("rb") as stream:
        header = stream.read(24)
        if len(header) != 24:
            raise ValueError("truncated pcap header")
        endian = "<" if header[:4] in {b"\xd4\xc3\xb2\xa1", b"M<\xb2\xa1"} else ">"
        origin: float | None = None
        while packet_header := stream.read(16):
            if len(packet_header) != 16:
                raise ValueError("truncated packet header")
            seconds, micros, captured, _ = struct.unpack(endian + "IIII", packet_header)
            packet = stream.read(captured)
            if len(packet) < 28:
                continue
            header_length = struct.unpack_from("<H", packet)[0]
            packet_device = struct.unpack_from("<H", packet, 19)[0]
            endpoint, transfer = packet[21:23]
            if packet_device != device or transfer != 2 or endpoint not in {0, 0x80}:
                continue
            payload = packet[header_length:]
            if not payload:
                continue
            timestamp = seconds + micros / 1_000_000
            origin = timestamp if origin is None else origin
            transfers.append(
                {
                    "seconds": round(timestamp - origin, 6),
                    "endpoint": f"0x{endpoint:02x}",
                    "stage": packet[27],
                    "payload": payload.hex(),
                }
            )
    return transfers


def vendor_requests(path: Path, device: int = 1) -> list[dict[str, Any]]:
    """Return decoded vendor requests, pairing IN setup packets with responses."""

    requests: list[dict[str, Any]] = []
    pending_in: dict[str, Any] | None = None
    for event in control_transfers(path, device):
        payload = bytes.fromhex(str(event["payload"]))
        if len(payload) >= 8 and payload[0] in {0x40, 0xC0}:
            setup = payload[:8]
            length = int.from_bytes(setup[6:8], "little")
            request: dict[str, Any] = {
                "seconds": event["seconds"],
                "direction": "in" if setup[0] & 0x80 else "out",
                "request": f"0x{setup[1]:02x}",
                "value": f"0x{int.from_bytes(setup[2:4], 'little'):04x}",
                "index": f"0x{int.from_bytes(setup[4:6], 'little'):04x}",
                "length": length,
            }
            if request["direction"] == "out":
                request["data"] = payload[8 : 8 + length].hex()
            else:
                request["response"] = None
                pending_in = request
            requests.append(request)
            continue
        if pending_in is not None and event["endpoint"] == "0x80" and event["stage"] == 3:
            pending_in["response"] = payload.hex()
            pending_in = None
    return requests


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("captures", type=Path, nargs="+")
    parser.add_argument("--device", type=int, default=1)
    parser.add_argument(
        "--vendor-only",
        action="store_true",
        help="decode only vendor requests and pair control-IN responses",
    )
    args = parser.parse_args()
    reader = vendor_requests if args.vendor_only else control_transfers
    result = {path.name: reader(path, args.device) for path in args.captures}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
