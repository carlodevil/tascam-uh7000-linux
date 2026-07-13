#!/usr/bin/env python3
"""Validate research fixtures without promoting them to production controls."""

from __future__ import annotations

import json
from pathlib import Path

FIXTURES = Path(__file__).parents[1] / "research" / "windows-control-fixtures.json"


def main() -> int:
    fixture = json.loads(FIXTURES.read_text(encoding="utf-8"))
    if fixture["schema"] != "io.github.carlodevil.UH7000.WindowsControlFixtures.v1":
        raise ValueError("unexpected fixture schema")
    if fixture["global_rules"]["writes_enabled"] is not False:
        raise ValueError("research fixtures must never enable writes")
    for name, control in fixture["controls"].items():
        if control.get("request") != "0x4d":
            continue
        images = list(control.get("states", {}).values()) or [control["observed_image"]]
        for image in images:
            if len(bytes.fromhex(image)) != 64:
                raise ValueError(f"{name} contains a non-64-byte state image")
        if "changed_offsets" in control:
            values = list(control["states"].values())
            actual = [
                index
                for index, pair in enumerate(zip(*map(bytes.fromhex, values)))
                if len(set(pair)) > 1
            ]
            if actual != control["changed_offsets"]:
                raise ValueError(
                    f"{name} changed offsets mismatch: fixture={control['changed_offsets']}, actual={actual}"
                )
    print("Windows control fixtures are internally consistent and write-disabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
