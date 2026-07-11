from __future__ import annotations

import unittest

from uh7000.controller import Controller, UnverifiedControlError
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


if __name__ == "__main__":
    unittest.main()
