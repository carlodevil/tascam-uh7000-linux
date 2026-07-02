#!/usr/bin/env python3
"""Cautious UH-7000 vendor-control probe.

This tool is for protocol discovery. By default it does not write to vendor
endpoints. It can read descriptors, show kernel-driver state, and try short
bulk reads on the vendor interface.
"""

from __future__ import annotations

import argparse
import ctypes
import fcntl
import os
import sys
import time

import usb.core
import usb.util


VID = 0x0644
PID = 0x8048
VENDOR_IFACE = 3
BULK_IN = 0x83
INT_OUT = 0x04
VENDOR_DEVICE_IN = 0xC0
VENDOR_DEVICE_OUT = 0x40
UH7000_SELECTOR_REQUEST = 0x49
USBDEVFS_IOCTL_TYPE = ord("U")
USBDEVFS_IOCTL_NR_CONTROL = 0
IOC_WRITE = 1
IOC_READ = 2
IOC_DIRSHIFT = 30
IOC_SIZESHIFT = 16
IOC_TYPESHIFT = 8
IOC_NRSHIFT = 0


class UsbdevfsCtrlTransfer(ctypes.Structure):
    _fields_ = [
        ("bRequestType", ctypes.c_uint8),
        ("bRequest", ctypes.c_uint8),
        ("wValue", ctypes.c_uint16),
        ("wIndex", ctypes.c_uint16),
        ("wLength", ctypes.c_uint16),
        ("timeout", ctypes.c_uint32),
        ("data", ctypes.c_void_p),
    ]


USBDEVFS_CONTROL = (
    ((IOC_READ | IOC_WRITE) << IOC_DIRSHIFT)
    | (ctypes.sizeof(UsbdevfsCtrlTransfer) << IOC_SIZESHIFT)
    | (USBDEVFS_IOCTL_TYPE << IOC_TYPESHIFT)
    | (USBDEVFS_IOCTL_NR_CONTROL << IOC_NRSHIFT)
)


def hexdump(data: bytes, width: int = 16) -> str:
    lines: list[str] = []
    for off in range(0, len(data), width):
        chunk = data[off : off + width]
        hx = " ".join(f"{b:02x}" for b in chunk)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{off:04x}: {hx:<{width * 3}} {asc}")
    return "\n".join(lines)


def decode_status_packets(data: bytes) -> list[str]:
    decoded: list[str] = []
    for off in range(0, len(data) - 3, 4):
        packet = data[off : off + 4]
        if packet[0] == 0x0B and packet[1] == 0xB0:
            decoded.append(
                f"packet@{off}: prefix=0bb0 control=0x{packet[2]:02x} value=0x{packet[3]:02x}"
            )
        else:
            decoded.append(f"packet@{off}: raw={packet.hex()}")
    if len(data) % 4:
        decoded.append(f"trailing: {data[len(data) - (len(data) % 4):].hex()}")
    return decoded


def find_device() -> usb.core.Device:
    dev = usb.core.find(idVendor=VID, idProduct=PID)
    if dev is None:
        raise SystemExit("UH-7000 0644:8048 not found")
    return dev


def print_descriptors(dev: usb.core.Device) -> None:
    print(f"Device {dev.idVendor:04x}:{dev.idProduct:04x} bcd={dev.bcdDevice:04x}")
    try:
        print(f"manufacturer={usb.util.get_string(dev, dev.iManufacturer)}")
        print(f"product={usb.util.get_string(dev, dev.iProduct)}")
        print(f"serial={usb.util.get_string(dev, dev.iSerialNumber)}")
    except (ValueError, usb.core.USBError) as exc:
        print(f"string read failed: {exc}")

    for cfg in dev:
        print(f"\nConfiguration {cfg.bConfigurationValue}: interfaces={cfg.bNumInterfaces}")
        for intf in cfg:
            eps = " ".join(
                f"0x{ep.bEndpointAddress:02x}/attr=0x{ep.bmAttributes:02x}/max={ep.wMaxPacketSize}"
                for ep in intf
            )
            print(
                "  "
                f"if={intf.bInterfaceNumber} alt={intf.bAlternateSetting} "
                f"class=0x{intf.bInterfaceClass:02x} "
                f"sub=0x{intf.bInterfaceSubClass:02x} "
                f"proto=0x{intf.bInterfaceProtocol:02x} eps=[{eps}]"
            )


def kernel_driver_state(dev: usb.core.Device) -> None:
    print("\nKernel driver state:")
    for iface in range(4):
        try:
            active = dev.is_kernel_driver_active(iface)
        except (NotImplementedError, usb.core.USBError) as exc:
            print(f"  iface {iface}: unknown ({exc})")
        else:
            print(f"  iface {iface}: {'active' if active else 'not active'}")


def claim_vendor_interface(dev: usb.core.Device, detach: bool) -> bool:
    try:
        active = dev.is_kernel_driver_active(VENDOR_IFACE)
        if active and detach:
            print(f"Detaching kernel driver from interface {VENDOR_IFACE}")
            dev.detach_kernel_driver(VENDOR_IFACE)
        elif active:
            print(f"Interface {VENDOR_IFACE} has active kernel driver; not detaching")
            return False
    except (NotImplementedError, usb.core.USBError) as exc:
        print(f"Kernel-driver check for interface {VENDOR_IFACE} failed: {exc}")

    try:
        usb.util.claim_interface(dev, VENDOR_IFACE)
        return True
    except usb.core.USBError as exc:
        print(f"Claim interface {VENDOR_IFACE} failed: {exc}")
        return False


def bulk_read_probe(dev: usb.core.Device, timeout_ms: int, count: int) -> None:
    print(f"\nBulk read probe ep=0x{BULK_IN:02x} count={count} timeout={timeout_ms}ms")
    for i in range(count):
        try:
            data = bytes(dev.read(BULK_IN, 512, timeout=timeout_ms))
        except usb.core.USBTimeoutError:
            print(f"  read {i}: timeout")
        except usb.core.USBError as exc:
            print(f"  read {i}: USBError {exc}")
        else:
            print(f"  read {i}: {len(data)} bytes")
            print(hexdump(data))
            for line in decode_status_packets(data):
                print(f"    {line}")


def send_status_packet(dev: usb.core.Device, control: int, value: int, timeout_ms: int) -> None:
    packet = bytes((0x0B, 0xB0, control & 0xFF, value & 0xFF))
    print(f"\nInterrupt OUT write ep=0x{INT_OUT:02x}: {packet.hex()} control=0x{control:02x} value=0x{value:02x}")
    written = dev.write(INT_OUT, packet, timeout=timeout_ms)
    print(f"  wrote {written} bytes")


def usbfs_device_path(dev: usb.core.Device) -> str:
    return f"/dev/bus/usb/{dev.bus:03d}/{dev.address:03d}"


def usbfs_control_transfer(
    dev: usb.core.Device,
    request_type: int,
    request: int,
    value: int,
    index: int,
    payload: bytes,
    timeout_ms: int,
) -> int:
    buf = ctypes.create_string_buffer(payload, len(payload))
    transfer = UsbdevfsCtrlTransfer(
        request_type & 0xFF,
        request & 0xFF,
        value & 0xFFFF,
        index & 0xFFFF,
        len(payload),
        timeout_ms,
        ctypes.cast(buf, ctypes.c_void_p).value,
    )
    path = usbfs_device_path(dev)
    fd = os.open(path, os.O_RDWR)
    try:
        return fcntl.ioctl(fd, USBDEVFS_CONTROL, transfer)
    finally:
        os.close(fd)


def selector_status_read(dev: usb.core.Device, timeout_ms: int) -> int:
    try:
        payload = usbfs_control_read(
            dev,
            VENDOR_DEVICE_IN,
            UH7000_SELECTOR_REQUEST,
            0,
            0,
            1,
            timeout_ms,
        )
    except OSError as exc:
        raise SystemExit(f"selector status read failed: {exc}") from exc
    value = payload[0]
    print(f"\nUH-7000 selector status read: 0x{value:02x}")
    return value


def selector_status_write(dev: usb.core.Device, value: int, timeout_ms: int) -> None:
    if value < 0 or value > 0xFF:
        raise SystemExit("selector status value must fit one byte")
    print(f"\nUH-7000 selector status write: 0x{value:02x}")
    try:
        transferred = usbfs_control_transfer(
            dev,
            VENDOR_DEVICE_OUT,
            UH7000_SELECTOR_REQUEST,
            value,
            0,
            b"",
            timeout_ms,
        )
    except OSError as exc:
        raise SystemExit(f"selector status write failed: {exc}") from exc
    print(f"  transferred {transferred} bytes")


def usbfs_control_read(
    dev: usb.core.Device,
    request_type: int,
    request: int,
    value: int,
    index: int,
    length: int,
    timeout_ms: int,
) -> bytes:
    buf = ctypes.create_string_buffer(length)
    transfer = UsbdevfsCtrlTransfer(
        request_type & 0xFF,
        request & 0xFF,
        value & 0xFFFF,
        index & 0xFFFF,
        length,
        timeout_ms,
        ctypes.cast(buf, ctypes.c_void_p).value,
    )
    path = usbfs_device_path(dev)
    fd = os.open(path, os.O_RDWR)
    try:
        transferred = fcntl.ioctl(fd, USBDEVFS_CONTROL, transfer)
    finally:
        os.close(fd)
    return bytes(buf.raw[:transferred])


def parse_int(text: str) -> int:
    try:
        return int(text, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid integer {text!r}") from exc


def parse_vendor_read(text: str) -> tuple[int, int, int, int, int]:
    parts = text.split(":")
    if len(parts) not in (4, 5):
        raise argparse.ArgumentTypeError(
            "expected REQUEST:WVALUE:WINDEX:LENGTH[:REQUEST_TYPE]"
        )
    request, value, index, length = (parse_int(part) for part in parts[:4])
    request_type = parse_int(parts[4]) if len(parts) == 5 else VENDOR_DEVICE_IN
    return request_type, request, value, index, length


def parse_vendor_write(text: str) -> tuple[int, int, int, bytes, int]:
    parts = text.split(":")
    if len(parts) not in (4, 5):
        raise argparse.ArgumentTypeError(
            "expected REQUEST:WVALUE:WINDEX:HEX_PAYLOAD[:REQUEST_TYPE]"
        )
    request, value, index = (parse_int(part) for part in parts[:3])
    hex_payload = parts[3].replace(" ", "")
    if len(hex_payload) % 2:
        raise argparse.ArgumentTypeError("hex payload must have an even number of digits")
    try:
        payload = bytes.fromhex(hex_payload)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("payload is not valid hex") from exc
    request_type = parse_int(parts[4]) if len(parts) == 5 else VENDOR_DEVICE_OUT
    return request_type, request, value, index, payload


def vendor_read_probe(
    dev: usb.core.Device,
    request_type: int,
    request: int,
    value: int,
    index: int,
    length: int,
    timeout_ms: int,
) -> bytes:
    print(
        "\nVendor control read: "
        f"bm=0x{request_type:02x} req=0x{request:02x} "
        f"wValue=0x{value:04x} wIndex=0x{index:04x} length={length}"
    )
    try:
        payload = usbfs_control_read(
            dev, request_type, request, value, index, length, timeout_ms
        )
    except OSError as exc:
        print(f"  failed: {exc}")
        return b""
    print(f"  transferred {len(payload)} bytes")
    if payload:
        print(hexdump(payload))
    return payload


def vendor_write_probe(
    dev: usb.core.Device,
    request_type: int,
    request: int,
    value: int,
    index: int,
    payload: bytes,
    timeout_ms: int,
) -> int:
    print(
        "\nVendor control write: "
        f"bm=0x{request_type:02x} req=0x{request:02x} "
        f"wValue=0x{value:04x} wIndex=0x{index:04x} length={len(payload)}"
    )
    try:
        transferred = usbfs_control_transfer(
            dev, request_type, request, value, index, payload, timeout_ms
        )
    except OSError as exc:
        print(f"  failed: {exc}")
        return -1
    print(f"  transferred {transferred} bytes")
    return transferred


def parse_packet_arg(raw: str) -> tuple[int, int]:
    try:
        control_s, value_s = raw.split(":", 1)
        return int(control_s, 0), int(value_s, 0)
    except Exception as exc:
        raise argparse.ArgumentTypeError("expected CONTROL:VALUE, e.g. 0x6b:0x7f") from exc


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bulk-read", action="store_true", help="try short reads from vendor bulk IN endpoint")
    parser.add_argument("--detach", action="store_true", help="detach kernel driver from vendor interface if needed")
    parser.add_argument("--bulk-count", type=int, default=3)
    parser.add_argument("--timeout-ms", type=int, default=200)
    parser.add_argument(
        "--send-packet",
        action="append",
        type=parse_packet_arg,
        default=[],
        metavar="CONTROL:VALUE",
        help="send explicit 0b b0 CONTROL VALUE packet to interrupt OUT endpoint",
    )
    parser.add_argument(
        "--selector-status-read",
        action="store_true",
        help="read the UH-7000 vendor selector byte (Windows request 0x49)",
    )
    parser.add_argument(
        "--selector-status-write",
        type=lambda s: int(s, 0),
        metavar="VALUE",
        help="write the UH-7000 vendor selector byte (Windows request 0x49)",
    )
    parser.add_argument(
        "--vendor-read",
        action="append",
        type=parse_vendor_read,
        help="explicit vendor read REQUEST:WVALUE:WINDEX:LENGTH[:REQUEST_TYPE]",
    )
    parser.add_argument(
        "--vendor-write",
        action="append",
        type=parse_vendor_write,
        help="explicit vendor write REQUEST:WVALUE:WINDEX:HEX_PAYLOAD[:REQUEST_TYPE]",
    )
    args = parser.parse_args(argv)

    dev = find_device()
    print_descriptors(dev)
    kernel_driver_state(dev)

    needs_interface = args.bulk_read or args.send_packet
    if needs_interface:
        if not claim_vendor_interface(dev, detach=args.detach):
            return 2

    if args.selector_status_read:
        selector_status_read(dev, args.timeout_ms)
    if args.selector_status_write is not None:
        selector_status_write(dev, args.selector_status_write, args.timeout_ms)

    for read_args in args.vendor_read or []:
        vendor_read_probe(dev, *read_args, timeout_ms=args.timeout_ms)
    for write_args in args.vendor_write or []:
        vendor_write_probe(dev, *write_args, timeout_ms=args.timeout_ms)

    for control, value in args.send_packet:
        send_status_packet(dev, control, value, args.timeout_ms)

    if args.bulk_read:
        bulk_read_probe(dev, args.timeout_ms, args.bulk_count)

    time.sleep(0.05)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
