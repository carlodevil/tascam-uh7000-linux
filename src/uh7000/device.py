"""USB discovery and the verified read-only UH-7000 transport."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from .models import DeviceStatus
from .protocol import PID, REQUEST_TYPE_VENDOR_IN, VID

SYSFS_USB_ROOT = Path("/sys/bus/usb/devices")


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return None


def _read_int(path: Path) -> int | None:
    value = _read_text(path)
    if value is None:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def discover_sysfs(root: Path = SYSFS_USB_ROOT) -> list[Path]:
    devices: list[Path] = []
    if not root.exists():
        return devices
    for path in sorted(root.iterdir()):
        if _read_text(path / "idVendor") != f"{VID:04x}":
            continue
        if _read_text(path / "idProduct") != f"{PID:04x}":
            continue
        devices.append(path)
    return devices


def _driver_bound(path: Path) -> bool:
    parent = path.parent
    prefix = f"{path.name}:"
    try:
        interfaces: Iterable[Path] = parent.iterdir()
    except OSError:
        return False
    for interface in interfaces:
        if interface.name.startswith(prefix) and (interface / "driver").exists():
            try:
                if "snd-usb-audio" in os.path.realpath(interface / "driver"):
                    return True
            except OSError:
                continue
    return False


def device_status(root: Path = SYSFS_USB_ROOT) -> DeviceStatus:
    devices = discover_sysfs(root)
    if not devices:
        return DeviceStatus(connected=False, error="UH-7000 0644:8048 not found")
    if len(devices) > 1:
        return DeviceStatus(
            connected=True,
            error="multiple UH-7000 devices are unsupported because they have no unique serial",
        )
    path = devices[0]
    speed = _read_int(path / "speed")
    return DeviceStatus(
        connected=True,
        sysfs_path=str(path),
        bus_number=_read_int(path / "busnum"),
        device_number=_read_int(path / "devnum"),
        usb_configuration=_read_int(path / "bConfigurationValue"),
        usb_speed_mbps=speed,
        driver_bound=_driver_bound(path),
    )


class PyUsbTransport:
    """PyUSB transport restricted to verified vendor reads."""

    def __init__(self) -> None:
        try:
            import usb.core  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("PyUSB is required for UH-7000 control access") from exc
        device = usb.core.find(idVendor=VID, idProduct=PID)
        if device is None:
            raise FileNotFoundError("UH-7000 0644:8048 not found")
        self._device = device

    def control_read(
        self,
        request: int,
        value: int,
        index: int,
        length: int,
        timeout_ms: int = 1000,
    ) -> bytes:
        payload = self._device.ctrl_transfer(
            REQUEST_TYPE_VENDOR_IN,
            request,
            value,
            index,
            length,
            timeout=timeout_ms,
        )
        return bytes(payload)


def select_configuration_two(path: Path) -> None:
    """Root-only primitive used by the hot-plug helper."""
    if (
        _read_text(path / "idVendor") != f"{VID:04x}"
        or _read_text(path / "idProduct") != f"{PID:04x}"
    ):
        raise ValueError("refusing to configure a device that is not 0644:8048")
    config_path = path / "bConfigurationValue"
    if _read_int(config_path) == 2:
        return
    config_path.write_text("2", encoding="ascii")
