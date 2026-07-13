#!/usr/bin/env python3
"""Build a compact, reproducible manifest from UH-7000 USBPcap files."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from parse_usbpcap import vendor_requests


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture_directory", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--device", type=int, default=1)
    args = parser.parse_args()

    captures = {}
    for path in sorted(args.capture_directory.glob("*.pcap")):
        requests = vendor_requests(path, args.device)
        captures[path.name] = {
            "sha256": sha256(path),
            "size": path.stat().st_size,
            "vendor_request_count": len(requests),
            "vendor_requests": requests,
        }

    manifest = {
        "schema": "io.github.carlodevil.UH7000.WindowsCaptureManifest.v1",
        "device_address": args.device,
        "captures": captures,
    }
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
