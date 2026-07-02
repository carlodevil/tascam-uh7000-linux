#!/usr/bin/env python3
"""Decode immediate UH-7000 Windows driver USB-control call sites.

The Windows driver routes USB control transfers through helper 0xf1043310.
This script scans an objdump-style disassembly and reports only call sites
where the helper arguments are set from nearby immediate values.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


HELPER = "0xf1043310"

ADDR_RE = re.compile(r"^\s*([0-9a-f]+):")
CALL_HELPER_RE = re.compile(r"\bcall\s+0xf1043310\b")
STACK_BYTE_RE = re.compile(r"mov\s+BYTE PTR \[rsp\+0x([0-9a-f]+)\],0x([0-9a-f]+)")
STACK_WORD_RE = re.compile(r"mov\s+WORD PTR \[rsp\+0x([0-9a-f]+)\],0x([0-9a-f]+)")
STACK_DWORD_RE = re.compile(r"mov\s+DWORD PTR \[rsp\+0x([0-9a-f]+)\],0x([0-9a-f]+)")
STACK_STORE_RE = re.compile(r"mov\s+(BYTE|WORD|DWORD|QWORD) PTR \[rsp\+0x([0-9a-f]+)\],(.+)")
LEA_REG_STACK_RE = re.compile(r"lea\s+(rax|rcx|rdx|r8|r9),\[rsp\+0x([0-9a-f]+)\]")
STACK_QWORD_REG_RE = re.compile(r"mov\s+QWORD PTR \[rsp\+0x([0-9a-f]+)\],(rax|rcx|rdx|r8|r9)")
REG32_RE = re.compile(r"mov\s+(edx|r8d|r9d),0x([0-9a-f]+)")
REG16_RE = re.compile(r"mov\s+(dx|r8w|r9w),0x([0-9a-f]+)")
XOR_EDX_RE = re.compile(r"xor\s+edx,edx")

STORE_SIZES = {"BYTE": 1, "WORD": 2, "DWORD": 4, "QWORD": 8}


def clear_stack_range(stack: dict[int, int], offset: int, size: int) -> None:
    end = offset + size
    for key in list(stack):
        if offset <= key < end:
            del stack[key]


@dataclass(frozen=True)
class Instruction:
    addr: int
    text: str


@dataclass(frozen=True)
class Transfer:
    call_addr: int
    request: int
    value: int
    index: int
    length: int | None
    edx: int | None
    r8: int | None
    r9: int | None

    @property
    def family(self) -> str:
        if self.request == 0x01 and self.r8 == 0x20:
            return "USB class/interface-style request"
        if self.request in (0x40, 0x41, 0x42, 0x46, 0x48, 0x49, 0x4D, 0x54, 0x55):
            return "UH-7000 vendor control family"
        return "other helper call"

    def row(self) -> str:
        length = "?" if self.length is None else str(self.length)
        edx = "?" if self.edx is None else f"0x{self.edx:x}"
        r8 = "?" if self.r8 is None else f"0x{self.r8:x}"
        r9 = "?" if self.r9 is None else f"0x{self.r9:x}"
        return (
            f"0x{self.call_addr:08x}  req=0x{self.request:02x} "
            f"wValue=0x{self.value:04x} wIndex=0x{self.index:04x} "
            f"len={length:<3} edx={edx:<6} r8={r8:<6} r9={r9:<6} "
            f"{self.family}"
        )

    def markdown_row(self) -> str:
        length = "?" if self.length is None else str(self.length)
        edx = "?" if self.edx is None else f"0x{self.edx:x}"
        r8 = "?" if self.r8 is None else f"0x{self.r8:x}"
        r9 = "?" if self.r9 is None else f"0x{self.r9:x}"
        return (
            f"| `0x{self.call_addr:08x}` | `0x{self.request:02x}` | "
            f"`0x{self.value:04x}` | `0x{self.index:04x}` | {length} | "
            f"`{edx}` | `{r8}` | `{r9}` | {self.family} |"
        )


def parse_disassembly(path: Path) -> list[Instruction]:
    instructions: list[Instruction] = []
    for line in path.read_text(errors="replace").splitlines():
        match = ADDR_RE.match(line)
        if not match:
            continue
        instructions.append(Instruction(int(match.group(1), 16), line.split("\t")[-1]))
    return instructions


def previous_immediates(window: list[Instruction]) -> Transfer | None:
    stack: dict[int, int] = {}
    stack_pointers: dict[int, int] = {}
    regs: dict[str, int] = {}
    pointer_regs: dict[str, int] = {}

    for insn in window:
        if match := STACK_BYTE_RE.search(insn.text):
            stack[int(match.group(1), 16)] = int(match.group(2), 16)
            continue
        if match := STACK_WORD_RE.search(insn.text):
            stack[int(match.group(1), 16)] = int(match.group(2), 16)
            continue
        if match := STACK_DWORD_RE.search(insn.text):
            stack[int(match.group(1), 16)] = int(match.group(2), 16)
            continue
        if match := LEA_REG_STACK_RE.search(insn.text):
            pointer_regs[match.group(1)] = int(match.group(2), 16)
            continue
        if match := STACK_QWORD_REG_RE.search(insn.text):
            offset = int(match.group(1), 16)
            register = match.group(2)
            if register in pointer_regs:
                stack_pointers[offset] = pointer_regs[register]
            else:
                stack_pointers.pop(offset, None)
            continue
        if match := STACK_STORE_RE.search(insn.text):
            size = STORE_SIZES[match.group(1)]
            offset = int(match.group(2), 16)
            clear_stack_range(stack, offset, size)
            stack_pointers.pop(offset, None)
            continue
        if match := REG32_RE.search(insn.text):
            regs[match.group(1)] = int(match.group(2), 16)
            continue
        if match := REG16_RE.search(insn.text):
            reg = {"dx": "edx", "r8w": "r8d", "r9w": "r9d"}[match.group(1)]
            regs[reg] = int(match.group(2), 16)
            continue
        if XOR_EDX_RE.search(insn.text):
            regs["edx"] = 0

    required = (0x20, 0x28, 0x30)
    if any(offset not in stack for offset in required):
        return None

    length = None
    length_pointer = stack_pointers.get(0x40)
    if length_pointer is not None:
        length = stack.get(length_pointer)
    return Transfer(
        call_addr=window[-1].addr,
        request=stack[0x20],
        value=stack[0x28],
        index=stack[0x30],
        length=length,
        edx=regs.get("edx"),
        r8=regs.get("r8d"),
        r9=regs.get("r9d"),
    )


def decode(instructions: list[Instruction], window_size: int) -> list[Transfer]:
    transfers: list[Transfer] = []
    for idx, insn in enumerate(instructions):
        if not CALL_HELPER_RE.search(insn.text):
            continue
        window = instructions[max(0, idx - window_size) : idx + 1]
        transfer = previous_immediates(window)
        if transfer is not None:
            transfers.append(transfer)
    return transfers


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "disassembly",
        nargs="?",
        default="/tmp/uh7000u.dis",
        help="objdump-style UH-7000 Windows driver disassembly",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=40,
        help="number of preceding instructions to inspect for immediates",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="emit a Markdown table instead of plain text rows",
    )
    args = parser.parse_args()

    transfers = decode(parse_disassembly(Path(args.disassembly)), args.window)
    if args.markdown:
        print("| Call site | Request | wValue | wIndex | Length | edx | r8 | r9 | Notes |")
        print("| --- | --- | --- | --- | ---: | --- | --- | --- | --- |")
        for transfer in transfers:
            print(transfer.markdown_row())
    else:
        for transfer in transfers:
            print(transfer.row())
        print(f"\ndecoded {len(transfers)} immediate call sites")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
