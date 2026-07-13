from __future__ import annotations

import unittest
from unittest.mock import patch

from uh7000.controller import Controller, UnverifiedControlError
from uh7000.models import DeviceStatus
from uh7000.protocol import MemoryTransport, REQUEST_SELECTOR_STATUS
from uh7000.service import BUS_NAME, INTERFACE_NAME, OBJECT_PATH


class ServiceContractTests(unittest.TestCase):
    def test_versioned_bus_contract(self) -> None:
        self.assertEqual("io.github.carlodevil.UH7000.Control1", BUS_NAME)
        self.assertEqual(BUS_NAME, INTERFACE_NAME)
        self.assertEqual("/io/github/carlodevil/UH7000/Control1", OBJECT_PATH)

    def test_unverified_writes_fail_closed(self) -> None:
        controller = Controller()
        with self.assertRaises(UnverifiedControlError):
            controller.apply_mixer_patch({"direct_monitor_enabled": True})
        with self.assertRaises(UnverifiedControlError):
            controller.reset()
        with self.assertRaises(UnverifiedControlError):
            controller.apply_preset("adcdac")

    def test_clock_source_requires_confirmation_and_updates_state(self) -> None:
        transport = MemoryTransport(
            {(REQUEST_SELECTOR_STATUS, 0, 0, 1): [b"\x02", b"\x00"]}
        )
        controller = Controller(transport_factory=lambda: transport)
        with patch(
            "uh7000.controller.device_status",
            return_value=DeviceStatus(connected=True, usb_configuration=2),
        ):
            with self.assertRaises(UnverifiedControlError):
                controller.set_clock_source("internal", outputs_disconnected=False)
            state = controller.set_clock_source("internal", outputs_disconnected=True)
        self.assertEqual("internal", state.clock_source.value)
        self.assertEqual([0], [write[1] for write in transport.writes])

    def test_clock_source_rejects_active_analog_output_configuration(self) -> None:
        transport = MemoryTransport({(REQUEST_SELECTOR_STATUS, 0, 0, 1): [b"\x02"]})
        controller = Controller(transport_factory=lambda: transport)
        with patch(
            "uh7000.controller.device_status",
            return_value=DeviceStatus(connected=True, usb_configuration=1),
        ):
            with self.assertRaisesRegex(UnverifiedControlError, "configuration 2"):
                controller.set_clock_source("internal", outputs_disconnected=True)
        self.assertEqual([], transport.writes)


if __name__ == "__main__":
    unittest.main()
