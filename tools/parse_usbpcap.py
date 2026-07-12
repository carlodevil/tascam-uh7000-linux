#!/usr/bin/env python3
"""Summarize UH-7000 control transfers from classic USBPcap files."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("captures", type=Path, nargs="+")
    parser.add_argument("--device", type=int, default=1)
    args = parser.parse_args()
    result = {path.name: control_transfers(path, args.device) for path in args.captures}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
