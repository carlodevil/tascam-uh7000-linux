#!/usr/bin/env python3
"""Model UH-7000 Windows ISO output encoder routines.

The Windows USB driver chooses product-specific functions before submitting
playback samples to the isochronous OUT endpoint. This tool models the small
24-bit packing functions that were decoded from tuh7000u.sys so their channel
selection and byte order can be compared with Linux ALSA output.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


FUNCTIONS = {
    "std": {
        "address": "0xf106c850",
        "selection": "generic 24-bit little-endian packing",
        "description": "pack every 32-bit left-aligned source sample as S24_3LE",
    },
    "swap": {
        "address": "0xf106c930",
        "selection": "usbEncode24STD_Swap",
        "description": "pack stereo pairs in swapped order: source 1,0 then 3,2",
    },
    "uh7000": {
        "address": "0xf106cce0",
        "selection": "ISO OUT ENCODER PROD_TEAC_UH7000 branch when descriptor bit 0x40 is set",
        "description": "pack source slots 0,1, skip 2,3, then pack 4,5 for a 4-channel endpoint frame",
    },
}


def parse_slots(raw: str) -> list[int]:
    values = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        values.append(int(item, 0))
    if not values:
        raise argparse.ArgumentTypeError("at least one slot value is required")
    return values


def signed24(value: int) -> int:
    value &= 0xFFFFFF
    if value & 0x800000:
        value -= 1 << 24
    return value


def left_align_24(value: int) -> int:
    return signed24(value) << 8


def s24le_from_i32_left(sample: int) -> bytes:
    shifted = sample >> 8
    shifted &= 0xFFFFFF
    return bytes((shifted & 0xFF, (shifted >> 8) & 0xFF, (shifted >> 16) & 0xFF))


def encode_frame(mode: str, source_slots: list[int]) -> bytes:
    source = [left_align_24(value) for value in source_slots]
    if mode == "std":
        selected = source[:4]
    elif mode == "swap":
        if len(source) < 4:
            raise ValueError("swap mode needs at least 4 source slots")
        selected = [source[1], source[0], source[3], source[2]]
    elif mode == "uh7000":
        if len(source) < 6:
            raise ValueError("uh7000 mode needs at least 6 source slots")
        selected = [source[0], source[1], source[4], source[5]]
    else:
        raise ValueError(f"unknown mode {mode}")
    return b"".join(s24le_from_i32_left(sample) for sample in selected)


def db_to_amplitude(dbfs: int) -> float:
    return 10 ** (dbfs / 20.0)


def tone_slots(frame: int, rate: int, frequency: float, dbfs: int, slot_count: int) -> list[int]:
    amplitude = db_to_amplitude(dbfs)
    sample = int(
        max(-0.999, min(0.999, amplitude * math.sin(2 * math.pi * frequency * frame / rate)))
        * 8388607
    )
    return [sample] * slot_count


def write_tone(path: Path, mode: str, frames: int, rate: int, frequency: float, dbfs: int) -> None:
    slot_count = 8 if mode == "uh7000" else 4
    with path.open("wb") as handle:
        for frame in range(frames):
            handle.write(encode_frame(mode, tone_slots(frame, rate, frequency, dbfs, slot_count)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=sorted(FUNCTIONS), default="uh7000")
    parser.add_argument(
        "--slots",
        type=parse_slots,
        default=parse_slots("0x010000,0x020000,0x030000,0x040000,0x050000,0x060000,0x070000,0x080000"),
        help="comma-separated signed 24-bit source slot values for one frame",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--tone-raw", type=Path, help="write a 4-channel S24_3LE tone file")
    parser.add_argument("--frames", type=int, default=48000)
    parser.add_argument("--rate", type=int, default=48000)
    parser.add_argument("--frequency", type=float, default=1000.0)
    parser.add_argument("--dbfs", type=int, default=-60)
    args = parser.parse_args()

    frame = encode_frame(args.mode, args.slots)
    result = {
        "schema": "tascam-uh7000-iso-encoder-v1",
        "mode": args.mode,
        "function": FUNCTIONS[args.mode],
        "source_slots_24bit": [f"0x{value & 0xffffff:06x}" for value in args.slots],
        "endpoint_channels": 4,
        "endpoint_format": "S24_3LE",
        "encoded_frame_hex": frame.hex(),
        "encoded_frame_bytes": len(frame),
        "notes": [
            "Windows source samples are modeled as 24-bit values left-aligned in signed 32-bit words.",
            "The UH-7000 encoder branch selects virtual source slots 0,1,4,5 for one 4-channel endpoint frame.",
            "A tone present in every ALSA channel should survive channel-order changes, so total silence still points beyond simple channel swapping.",
        ],
    }
    if args.tone_raw:
        write_tone(args.tone_raw, args.mode, args.frames, args.rate, args.frequency, args.dbfs)
        result["tone_raw"] = {
            "path": str(args.tone_raw),
            "frames": args.frames,
            "rate": args.rate,
            "frequency": args.frequency,
            "dbfs": args.dbfs,
            "bytes": args.tone_raw.stat().st_size,
            "aplay_command": (
                f"aplay -t raw -D hw:UH7000,0 -f S24_3LE -c 4 -r {args.rate} {args.tone_raw}"
            ),
        }
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return

    print(f"schema={result['schema']}")
    print(f"mode={args.mode}")
    print(f"function={FUNCTIONS[args.mode]['address']}")
    print(f"encoded_frame_hex={frame.hex()}")
    if args.tone_raw:
        print(f"tone_raw={args.tone_raw}")
        print(result["tone_raw"]["aplay_command"])


if __name__ == "__main__":
    main()
