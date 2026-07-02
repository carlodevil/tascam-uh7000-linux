#!/usr/bin/env python3
"""Emulate small UH-7000 control-panel routines for protocol research."""

from __future__ import annotations

import argparse
import hashlib
import json
import mmap
import struct
from pathlib import Path

import pefile
from unicorn import Uc, UcError, UC_ARCH_X86, UC_HOOK_CODE, UC_MODE_64
from unicorn.x86_const import (
    UC_X86_REG_R8,
    UC_X86_REG_R9,
    UC_X86_REG_RAX,
    UC_X86_REG_RCX,
    UC_X86_REG_RDX,
    UC_X86_REG_RIP,
    UC_X86_REG_RSP,
)


IMAGE_BASE = 0x140000000
STACK_BASE = 0x180000000
STACK_SIZE = 0x200000
HEAP_BASE = 0x190000000
HEAP_SIZE = 0x200000
RETURN_SENTINEL = 0x1FFF0000

ADDR_SECURITY_CHECK = 0x140275E60
ADDR_MEMCPY = 0x140275F70
ADDR_MEMSET = 0x140276D70
ADDR_MEMCMP = 0x140279C00

ADDR_INIT_STATE = 0x140033460
ADDR_SET_INPUT_SEL = 0x140033E00
ADDR_SET_OUTPUT_SEL = 0x140033E90
ADDR_SET_MONITOR_MODE = 0x140033F20
ADDR_SET_STEREO_LINK = 0x1400114B0
ADDR_SET_DAC_MODE = 0x140011860
ADDR_BUILD_RATE = 0x140035A60
ADDR_PRESET = 0x140012FD0
ADDR_REFRESH_1 = 0x1400194B0
ADDR_REFRESH_2 = 0x140014420

F800_IMAGE_BASE = 0xF800
F800_RATE_TABLE = (0xAC44, 0xBB80, 0x15888, 0x17700, 0x2B110, 0x2EE00)


def align_down(value: int, size: int = 0x1000) -> int:
    return value & ~(size - 1)


def align_up(value: int, size: int = 0x1000) -> int:
    return (value + size - 1) & ~(size - 1)


class Emulator:
    def __init__(self, exe: Path) -> None:
        self.pe = pefile.PE(str(exe))
        self.mu = Uc(UC_ARCH_X86, UC_MODE_64)
        self._map_image()
        self.mu.mem_map(STACK_BASE, STACK_SIZE)
        self.mu.mem_map(HEAP_BASE, HEAP_SIZE)
        self.mu.mem_map(align_down(RETURN_SENTINEL), 0x1000)
        self.mu.hook_add(UC_HOOK_CODE, self._hook_code)

    def _map_image(self) -> None:
        size = align_up(self.pe.OPTIONAL_HEADER.SizeOfImage)
        self.mu.mem_map(IMAGE_BASE, size)
        headers = self.pe.get_memory_mapped_image()[: self.pe.OPTIONAL_HEADER.SizeOfHeaders]
        self.mu.mem_write(IMAGE_BASE, headers)
        for section in self.pe.sections:
            va = IMAGE_BASE + section.VirtualAddress
            raw = section.get_data()
            virtual_size = max(section.Misc_VirtualSize, len(raw))
            self.mu.mem_write(va, raw.ljust(virtual_size, b"\x00"))

    def _read_qword(self, addr: int) -> int:
        return struct.unpack("<Q", self.mu.mem_read(addr, 8))[0]

    def _write_qword(self, addr: int, value: int) -> None:
        self.mu.mem_write(addr, struct.pack("<Q", value & 0xFFFFFFFFFFFFFFFF))

    def _ret(self, value: int | None = None) -> None:
        if value is not None:
            self.mu.reg_write(UC_X86_REG_RAX, value & 0xFFFFFFFFFFFFFFFF)
        rsp = self.mu.reg_read(UC_X86_REG_RSP)
        rip = self._read_qword(rsp)
        self.mu.reg_write(UC_X86_REG_RSP, rsp + 8)
        self.mu.reg_write(UC_X86_REG_RIP, rip)

    def _hook_code(self, mu: Uc, address: int, _size: int, _user_data: object) -> None:
        if address == RETURN_SENTINEL:
            mu.emu_stop()
            return
        if address == ADDR_SECURITY_CHECK:
            self._ret()
            return
        if address == ADDR_MEMSET:
            dst = mu.reg_read(UC_X86_REG_RCX)
            value = mu.reg_read(UC_X86_REG_RDX) & 0xFF
            length = mu.reg_read(UC_X86_REG_R8)
            mu.mem_write(dst, bytes([value]) * length)
            self._ret(dst)
            return
        if address == ADDR_MEMCPY:
            dst = mu.reg_read(UC_X86_REG_RCX)
            src = mu.reg_read(UC_X86_REG_RDX)
            length = mu.reg_read(UC_X86_REG_R8)
            mu.mem_write(dst, bytes(mu.mem_read(src, length)))
            self._ret(dst)
            return
        if address == ADDR_MEMCMP:
            left = mu.reg_read(UC_X86_REG_RCX)
            right = mu.reg_read(UC_X86_REG_RDX)
            length = mu.reg_read(UC_X86_REG_R8)
            a = bytes(mu.mem_read(left, length))
            b = bytes(mu.mem_read(right, length))
            self._ret(0 if a == b else 1)
            return
        if address in (ADDR_REFRESH_1, ADDR_REFRESH_2):
            self._ret(1)

    def call(
        self,
        addr: int,
        rcx: int = 0,
        rdx: int = 0,
        r8: int = 0,
        r9: int = 0,
        stack_args: list[int] | None = None,
    ) -> int:
        stack_args = stack_args or []
        rsp = STACK_BASE + STACK_SIZE - 0x1000
        self._write_qword(rsp, RETURN_SENTINEL)
        for i, value in enumerate(stack_args):
            self._write_qword(rsp + 0x28 + i * 8, value)
        self.mu.reg_write(UC_X86_REG_RSP, rsp)
        self.mu.reg_write(UC_X86_REG_RCX, rcx)
        self.mu.reg_write(UC_X86_REG_RDX, rdx)
        self.mu.reg_write(UC_X86_REG_R8, r8)
        self.mu.reg_write(UC_X86_REG_R9, r9)
        try:
            self.mu.emu_start(addr, RETURN_SENTINEL)
        except UcError as exc:
            rip = self.mu.reg_read(UC_X86_REG_RIP)
            raise RuntimeError(f"emulation failed at 0x{rip:x}: {exc}") from exc
        return self.mu.reg_read(UC_X86_REG_RAX)

    def read(self, addr: int, length: int) -> bytes:
        return bytes(self.mu.mem_read(addr, length))

    def write_u32(self, addr: int, value: int) -> None:
        self.mu.mem_write(addr, struct.pack("<I", value & 0xFFFFFFFF))


def parse_u32_assignment(value: str) -> tuple[int, int]:
    try:
        key, raw = value.split("=", 1)
        return int(key, 0), int(raw, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected OFFSET=VALUE") from exc


def summarize_block(data: bytes) -> dict[str, object]:
    nonzero_offsets = [i for i, value in enumerate(data) if value]
    first_nonzero = nonzero_offsets[0] if nonzero_offsets else None
    last_nonzero = nonzero_offsets[-1] if nonzero_offsets else None
    return {
        "length": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "nonzero_bytes": len(nonzero_offsets),
        "first_nonzero": first_nonzero,
        "last_nonzero": last_nonzero,
        "head_hex": data[:64].hex(),
    }


def write_be16(buf: bytearray, offset: int, value: int) -> None:
    buf[offset : offset + 2] = (value & 0xFFFF).to_bytes(2, "big")


def write_be32(buf: bytearray, offset: int, value: int) -> None:
    buf[offset : offset + 4] = (value & 0xFFFFFFFF).to_bytes(4, "big")


def image_sum_be_words(data: bytes) -> int:
    if len(data) % 4:
        raise ValueError("image length must be dword aligned")
    total = 0
    for offset in range(0, len(data), 4):
        total = (total + int.from_bytes(data[offset : offset + 4], "big")) & 0xFFFFFFFF
    return total


def decode_routing_block(data: bytes) -> dict[str, object]:
    slices = []
    compact_slots = []
    for index in range(8):
        chunk = data[index * 64 : (index + 1) * 64]
        nonzero = [
            {
                "offset": offset,
                "offset_hex": f"0x{offset:02x}",
                "value": value,
                "value_hex": f"0x{value:02x}",
            }
            for offset, value in enumerate(chunk)
            if value
        ]
        hot_slot = None
        lane = None
        if len(nonzero) == 1 and nonzero[0]["value"] == 0x40:
            offset = int(nonzero[0]["offset"])
            hot_slot = offset // 8
            lane = offset % 8
            compact_slots.append(str(hot_slot))
        else:
            compact_slots.append("mixed" if nonzero else "empty")
        slices.append(
            {
                "slice": index,
                "nonzero": nonzero,
                "hot_slot": hot_slot,
                "lane": lane,
            }
        )
    return {
        "slice_size": 64,
        "slice_count": 8,
        "compact_slots": compact_slots,
        "compact": ",".join(compact_slots),
        "slices": slices,
    }


def build_f800_image(
    exe: Path,
    *,
    preset: str,
    manual_preset: bool = False,
    current_rate: int,
    build_dl: int = 0,
    build_r8: int = 0,
    build_r9: int = 0,
    set_u32: list[tuple[int, int]] | None = None,
    set_input: int | None = None,
    set_output: int | None = None,
    set_monitor: int | None = None,
    footer_mode: str = "uac2",
    clock_word: int = 0,
    legacy_word: int = 0,
) -> tuple[bytes, dict[str, object]]:
    """Build the 0xf800 upload image without sending it to hardware.

    This mirrors the Cpl_UH7000.exe path that fills an 0x800-byte image before
    passing it to the 0x1004-byte Windows DeviceIoControl wrapper. The wrapper
    and request 0x55 page writes are intentionally not emulated here.
    """

    set_u32 = set_u32 or []
    emu = Emulator(exe)
    outer = HEAP_BASE + 0x10000
    state = outer + 0x10
    apply_preset(emu, outer, state, preset, manual_preset)

    if set_input is not None:
        emu.call(ADDR_SET_INPUT_SEL, state, set_input)
    if set_output is not None:
        emu.call(ADDR_SET_OUTPUT_SEL, state, set_output)
    if set_monitor is not None:
        emu.call(ADDR_SET_MONITOR_MODE, state, set_monitor)
    for offset, value in set_u32:
        emu.write_u32(state + offset, value)

    image = bytearray(0x800)
    rate_blocks = []
    for index, rate in enumerate(F800_RATE_TABLE):
        flags = emu.call(
            ADDR_BUILD_RATE,
            state,
            build_dl,
            build_r8,
            build_r9,
            [rate],
        )
        block = emu.read(state + 0x44C, 0x100)
        image[index * 0x100 : (index + 1) * 0x100] = block
        rate_blocks.append(
            {
                "index": index,
                "rate": rate,
                "rate_hex": f"0x{rate:x}",
                "image_offset": f"0x{index * 0x100:03x}",
                "flags": flags,
                "flags_hex": f"0x{flags:x}",
                **summarize_block(block),
            }
        )

    current_flags = emu.call(
        ADDR_BUILD_RATE,
        state,
        build_dl,
        build_r8,
        build_r9,
        [current_rate],
    )
    current_4d = emu.read(state + 0x40C, 0x40)
    image[0x600:0x640] = current_4d

    footer: dict[str, object] = {
        "mode": footer_mode,
        "current_rate": current_rate,
        "current_rate_hex": f"0x{current_rate:x}",
    }
    if footer_mode == "uac2":
        write_be32(image, 0x7F0, current_rate)
        write_be16(image, 0x7FA, clock_word)
        footer["rate_offset"] = "0x7f0"
        footer["clock_word"] = clock_word
        footer["clock_word_hex"] = f"0x{clock_word:x}"
        footer["clock_word_offset"] = "0x7fa"
    else:
        write_be32(image, 0x7F8, legacy_word)
        write_be16(image, 0x7FA, clock_word)
        footer["legacy_word"] = legacy_word
        footer["legacy_word_hex"] = f"0x{legacy_word:x}"
        footer["legacy_word_offset"] = "0x7f8"
        footer["clock_word"] = clock_word
        footer["clock_word_hex"] = f"0x{clock_word:x}"
        footer["clock_word_offset"] = "0x7fa"

    partial_sum = image_sum_be_words(image[:0x7FC])
    checksum = (-partial_sum) & 0xFFFFFFFF
    write_be32(image, 0x7FC, checksum)
    verify_sum = image_sum_be_words(image)
    footer["checksum_offset"] = "0x7fc"
    footer["checksum"] = checksum
    footer["checksum_hex"] = f"0x{checksum:08x}"
    footer["checksum_verify_sum"] = verify_sum
    footer["checksum_verify_sum_hex"] = f"0x{verify_sum:08x}"

    image_bytes = bytes(image)
    page_summaries = []
    for index in range(4):
        page = (F800_IMAGE_BASE // 0x200) + index
        chunk = image_bytes[index * 0x200 : (index + 1) * 0x200]
        page_summaries.append(
            {
                "page": f"0x{page:04x}",
                "image_offset": f"0x{index * 0x200:03x}",
                **summarize_block(chunk),
            }
        )

    metadata = {
        "schema": "tascam-uh7000-f800-image-v1",
        "risk": "offline-only; no USB request was sent",
        "exe": str(exe),
        "preset": preset,
        "manual_preset": manual_preset,
        "settings": {
            "set_input": set_input,
            "set_output": set_output,
            "set_monitor": set_monitor,
            "set_u32": [
                {
                    "offset": offset,
                    "value": value,
                    "offset_hex": f"0x{offset:x}",
                    "value_hex": f"0x{value:x}",
                }
                for offset, value in set_u32
            ],
        },
        "build_args": {
            "rdx": build_dl,
            "r8": build_r8,
            "r9": build_r9,
        },
        "transport": {
            "windows_upload_wrapper": "0x14002e490",
            "windows_download_wrapper": "0x14002e5f0",
            "windows_upload_ioctl": "0x2200fc",
            "windows_download_ioctl": "0x220100",
            "windows_ioctl_buffer_length": 0x1004,
            "windows_image_base": f"0x{F800_IMAGE_BASE:04x}",
            "usb_request": "0x55",
            "usb_page_length": 0x200,
            "usb_pages": ["0x007c", "0x007d", "0x007e", "0x007f"],
        },
        "layout": {
            "image_length": len(image_bytes),
            "rate_block_offsets": [
                {
                    "rate": rate,
                    "rate_hex": f"0x{rate:x}",
                    "offset": f"0x{index * 0x100:03x}",
                    "length": 0x100,
                    "source_state_offset": "0x44c",
                }
                for index, rate in enumerate(F800_RATE_TABLE)
            ],
            "current_4d_offset": "0x600",
            "current_4d_length": 0x40,
            "current_4d_source_state_offset": "0x40c",
            "footer": footer,
        },
        "current_4d_flags": current_flags,
        "current_4d_flags_hex": f"0x{current_flags:x}",
        "blocks": {
            "rate_blocks_0x000_0x5ff": rate_blocks,
            "current_0x4d_block_0x600": summarize_block(current_4d),
            "full_image": summarize_block(image_bytes),
            "pages": page_summaries,
        },
        "payload_hex": {
            "current_0x4d_block_0x600": current_4d.hex(),
            "image_0xf800": image_bytes.hex(),
        },
    }
    return image_bytes, metadata


def apply_preset(emu: Emulator, outer: int, state: int, preset: str, manual_preset: bool) -> None:
    if manual_preset:
        emu.call(ADDR_INIT_STATE, state, 0, outer, 0, [0])
        if preset == "adc":
            input_sel = 0
            output_sel = 0x101
        else:
            input_sel = 0x102
            output_sel = 0x101
        emu.call(ADDR_SET_INPUT_SEL, state, input_sel)
        emu.call(ADDR_SET_OUTPUT_SEL, state, output_sel)
        emu.call(ADDR_SET_STEREO_LINK, outer, 0)
        if preset == "adcdac":
            emu.call(ADDR_SET_DAC_MODE, outer, 0)
    else:
        preset_id = 1 if preset == "adc" else 2
        emu.call(ADDR_PRESET, outer, preset_id)


def build_case(
    exe: Path,
    *,
    name: str = "single",
    preset: str,
    manual_preset: bool = False,
    rate: int,
    build_dl: int = 0,
    build_r8: int = 0,
    build_r9: int = 0,
    set_u32: list[tuple[int, int]] | None = None,
    set_input: int | None = None,
    set_output: int | None = None,
    set_monitor: int | None = None,
    risk: str = "offline-only",
) -> dict[str, object]:
    set_u32 = set_u32 or []
    emu = Emulator(exe)
    outer = HEAP_BASE + 0x10000
    state = outer + 0x10

    apply_preset(emu, outer, state, preset, manual_preset)

    if set_input is not None:
        emu.call(ADDR_SET_INPUT_SEL, state, set_input)
    if set_output is not None:
        emu.call(ADDR_SET_OUTPUT_SEL, state, set_output)
    if set_monitor is not None:
        emu.call(ADDR_SET_MONITOR_MODE, state, set_monitor)
    for offset, value in set_u32:
        emu.write_u32(state + offset, value)

    flags = emu.call(
        ADDR_BUILD_RATE,
        state,
        build_dl,
        build_r8,
        build_r9,
        [rate],
    )
    block20c = emu.read(state + 0x20C, 0x200)
    block4d = emu.read(state + 0x40C, 0x40)
    block42 = emu.read(state + 0x44C, 0x100)
    cached_a = emu.read(state + 0x570, 0x40)
    cached_b = emu.read(state + 0x5B0, 0x40)

    return {
        "name": name,
        "preset": preset,
        "manual_preset": manual_preset,
        "rate": rate,
        "build_args": {
            "rdx": build_dl,
            "r8": build_r8,
            "r9": build_r9,
        },
        "settings": {
            "set_input": set_input,
            "set_output": set_output,
            "set_monitor": set_monitor,
            "set_u32": [
                {
                    "offset": offset,
                    "value": value,
                    "offset_hex": f"0x{offset:x}",
                    "value_hex": f"0x{value:x}",
                }
                for offset, value in set_u32
            ],
        },
        "risk": risk,
        "flags": flags,
        "flags_hex": f"0x{flags:x}",
        "windows_write_mixer_data": {
            "copies_full_state": bool(flags & 0x1),
            "copies_routing_block_0x20c": bool(flags & 0x2),
            "sends_request_0x4d": bool(flags & 0x4),
            "sends_request_0x42": bool(flags & 0x8),
        },
        "blocks": {
            "0x20c": summarize_block(block20c),
            "0x40c_request_0x4d": summarize_block(block4d),
            "0x44c_request_0x42": summarize_block(block42),
            "0x570_cached_0x4d": summarize_block(cached_a),
            "0x5b0_cached": summarize_block(cached_b),
        },
        "routing_block_0x20c": decode_routing_block(block20c),
        "payload_hex": {
            "0x20c": block20c.hex(),
            "0x40c_request_0x4d": block4d.hex(),
            "0x44c_request_0x42": block42.hex(),
            "0x570_cached_0x4d": cached_a.hex(),
            "0x5b0_cached": cached_b.hex(),
        },
    }


def matrix_cases(rate: int, build_dl: int, build_r8: int, build_r9: int) -> list[dict[str, object]]:
    common = {
        "rate": rate,
        "build_dl": build_dl,
        "build_r8": build_r8,
        "build_r9": build_r9,
    }
    cases: list[dict[str, object]] = []

    for preset in ("adc", "adcdac"):
        cases.append(
            {
                **common,
                "name": f"{preset}/preset",
                "preset": preset,
                "manual_preset": False,
                "risk": "offline baseline",
            }
        )
        cases.append(
            {
                **common,
                "name": f"{preset}/manual-preset",
                "preset": preset,
                "manual_preset": True,
                "risk": "offline baseline",
            }
        )

    selector_values = (0x0, 0x1, 0x100, 0x101, 0x102, 0x201)
    for selector in selector_values:
        cases.append(
            {
                **common,
                "name": f"adcdac/input-0x{selector:x}",
                "preset": "adcdac",
                "set_input": selector,
                "risk": "offline selector candidate",
            }
        )
    for selector in selector_values:
        cases.append(
            {
                **common,
                "name": f"adcdac/output-0x{selector:x}",
                "preset": "adcdac",
                "set_output": selector,
                "risk": "offline selector candidate",
            }
        )

    for mode in range(4):
        cases.append(
            {
                **common,
                "name": f"adcdac/monitor-{mode}",
                "preset": "adcdac",
                "set_monitor": mode,
                "risk": "offline monitor candidate",
            }
        )

    for mode in range(9):
        cases.append(
            {
                **common,
                "name": f"adcdac/effect-0x204-{mode}",
                "preset": "adcdac",
                "set_u32": [(0x204, mode)],
                "risk": (
                    "research-only: 0x204=1 caused hard loopback clipping locally"
                    if mode
                    else "offline baseline"
                ),
            }
        )

    return cases


def build_matrix_case(exe: Path, case: dict[str, object]) -> dict[str, object]:
    try:
        return build_case(exe, **case)
    except Exception as exc:  # pragma: no cover - depends on proprietary CPL paths
        return {
            "name": case.get("name", "unknown"),
            "preset": case.get("preset"),
            "manual_preset": case.get("manual_preset", False),
            "rate": case.get("rate"),
            "settings": {
                "set_input": case.get("set_input"),
                "set_output": case.get("set_output"),
                "set_monitor": case.get("set_monitor"),
                "set_u32": [
                    {
                        "offset": offset,
                        "value": value,
                        "offset_hex": f"0x{offset:x}",
                        "value_hex": f"0x{value:x}",
                    }
                    for offset, value in case.get("set_u32", [])
                ],
            },
            "risk": case.get("risk", "offline-only"),
            "error": str(exc),
        }


def render_matrix_table(matrix: dict[str, object]) -> str:
    rows = [
        "# UH-7000 CPL Emulator Matrix",
        "",
        f"- Schema: `{matrix['schema']}`",
        f"- Rate argument: `{matrix['rate']}`",
        f"- Cases: `{len(matrix['cases'])}`",
        "",
        "| Case | Flags | 0x20c route slots | 0x20c nz | 0x4d nz | 0x42 nz | Sends 0x42 | Risk |",
        "| --- | --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for case in matrix["cases"]:
        if "error" in case:
            rows.append(
                "| {name} | error | - | - | - | - | - | {risk}: `{error}` |".format(
                    name=case["name"],
                    risk=case["risk"],
                    error=case["error"],
                )
            )
            continue
        blocks = case["blocks"]
        writes = case["windows_write_mixer_data"]
        rows.append(
            "| {name} | `{flags}` | `{slots}` | {nz20c} | {nz4d} | {nz42} | {send42} | {risk} |".format(
                name=case["name"],
                flags=case["flags_hex"],
                slots=case["routing_block_0x20c"]["compact"],
                nz20c=blocks["0x20c"]["nonzero_bytes"],
                nz4d=blocks["0x40c_request_0x4d"]["nonzero_bytes"],
                nz42=blocks["0x44c_request_0x42"]["nonzero_bytes"],
                send42="yes" if writes["sends_request_0x42"] else "no",
                risk=case["risk"],
            )
        )
    return "\n".join(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", default="/tmp/uh7000-payload/x64/Cpl_UH7000.exe")
    parser.add_argument("--preset", choices=("adc", "adcdac"), default="adcdac")
    parser.add_argument("--manual-preset", action="store_true")
    parser.add_argument("--rate", type=lambda s: int(s, 0), default=0xBB80)
    parser.add_argument("--build-dl", type=lambda s: int(s, 0), default=0)
    parser.add_argument("--build-r8", type=lambda s: int(s, 0), default=0)
    parser.add_argument("--build-r9", type=lambda s: int(s, 0), default=0)
    parser.add_argument("--set-u32", action="append", type=parse_u32_assignment, default=[])
    parser.add_argument("--set-input", type=lambda s: int(s, 0))
    parser.add_argument("--set-output", type=lambda s: int(s, 0))
    parser.add_argument("--set-monitor", type=lambda s: int(s, 0))
    parser.add_argument("--matrix", action="store_true", help="emit a bounded offline candidate matrix")
    parser.add_argument("--f800-image", action="store_true", help="emit the offline 0xf800 mixer image")
    parser.add_argument("--footer-mode", choices=("uac2", "legacy"), default="uac2")
    parser.add_argument("--clock-word", type=lambda s: int(s, 0), default=0)
    parser.add_argument("--legacy-word", type=lambda s: int(s, 0), default=0)
    parser.add_argument("--output", type=Path, help="write the 0x800-byte --f800-image payload")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of the legacy text dump")
    parser.add_argument("--markdown", action="store_true", help="render --matrix as a markdown table")
    args = parser.parse_args()

    exe = Path(args.exe)
    if args.f800_image:
        image, result = build_f800_image(
            exe,
            preset=args.preset,
            manual_preset=args.manual_preset,
            current_rate=args.rate,
            build_dl=args.build_dl,
            build_r8=args.build_r8,
            build_r9=args.build_r9,
            set_u32=args.set_u32,
            set_input=args.set_input,
            set_output=args.set_output,
            set_monitor=args.set_monitor,
            footer_mode=args.footer_mode,
            clock_word=args.clock_word,
            legacy_word=args.legacy_word,
        )
        if args.output:
            args.output.write_bytes(image)
            result["output"] = str(args.output)
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
            return
        print("schema=tascam-uh7000-f800-image-v1")
        print("risk=offline-only no USB request was sent")
        print(f"preset={result['preset']}")
        print(f"current_rate={args.rate}")
        print(f"sha256={result['blocks']['full_image']['sha256']}")
        print(f"nonzero_bytes={result['blocks']['full_image']['nonzero_bytes']}")
        print(f"checksum={result['layout']['footer']['checksum_hex']}")
        print(f"checksum_verify_sum={result['layout']['footer']['checksum_verify_sum_hex']}")
        print("pages=" + ",".join(page["page"] for page in result["blocks"]["pages"]))
        if args.output:
            print(f"output={args.output}")
        return

    if args.matrix:
        matrix = {
            "schema": "tascam-uh7000-cpl-matrix-v1",
            "exe": str(exe),
            "rate": args.rate,
            "build_args": {
                "rdx": args.build_dl,
                "r8": args.build_r8,
                "r9": args.build_r9,
            },
            "notes": [
                "Offline emulation only; this file is not evidence that a payload is safe to send.",
                "Windows WriteMixerData flag 0x8 means a case would send vendor request 0x42.",
                "Local hardware clipped hard after a nonzero 0x42 candidate; live tests require preflight first.",
            ],
            "cases": [
                build_matrix_case(exe, case)
                for case in matrix_cases(args.rate, args.build_dl, args.build_r8, args.build_r9)
            ],
        }
        if args.markdown:
            print(render_matrix_table(matrix))
        else:
            print(json.dumps(matrix, indent=2, sort_keys=True))
        return

    result = build_case(
        exe,
        preset=args.preset,
        manual_preset=args.manual_preset,
        rate=args.rate,
        build_dl=args.build_dl,
        build_r8=args.build_r8,
        build_r9=args.build_r9,
        set_u32=args.set_u32,
        set_input=args.set_input,
        set_output=args.set_output,
        set_monitor=args.set_monitor,
    )
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return

    print(f"flags={result['flags_hex']}")
    print(f"20c={result['payload_hex']['0x20c']}")
    print(f"4d={result['payload_hex']['0x40c_request_0x4d']}")
    print(f"42={result['payload_hex']['0x44c_request_0x42']}")
    print(f"cached570={result['payload_hex']['0x570_cached_0x4d']}")
    print(f"cached5b0={result['payload_hex']['0x5b0_cached']}")


if __name__ == "__main__":
    main()
