from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from uh7000.device import device_status, discover_sysfs


class DeviceTests(unittest.TestCase):
    def make_device(self, root: Path, name: str = "1-2") -> Path:
        path = root / name
        path.mkdir()
        (path / "idVendor").write_text("0644\n", encoding="ascii")
        (path / "idProduct").write_text("8048\n", encoding="ascii")
        (path / "bConfigurationValue").write_text("2\n", encoding="ascii")
        (path / "busnum").write_text("1\n", encoding="ascii")
        (path / "devnum").write_text("4\n", encoding="ascii")
        (path / "speed").write_text("480\n", encoding="ascii")
        return path

    def test_discovery_is_exact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = self.make_device(root)
            other = root / "1-3"
            other.mkdir()
            (other / "idVendor").write_text("0644", encoding="ascii")
            (other / "idProduct").write_text("0001", encoding="ascii")
            self.assertEqual([expected], discover_sysfs(root))

    def test_status_reads_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_device(root)
            status = device_status(root)
            self.assertTrue(status.connected)
            self.assertEqual(2, status.usb_configuration)
            self.assertEqual(480, status.usb_speed_mbps)

    def test_multiple_devices_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_device(root, "1-2")
            self.make_device(root, "1-3")
            status = device_status(root)
            self.assertIn("multiple", status.error or "")


if __name__ == "__main__":
    unittest.main()
