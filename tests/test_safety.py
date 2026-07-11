from __future__ import annotations

import unittest

from uh7000.models import AudioTopology, DeviceStatus, MixerState
from uh7000.safety import RampGuard, evaluate_preflight, guarded_ramp_levels, playback_channel_plan


class SafetyTests(unittest.TestCase):
    def ready_inputs(self) -> tuple[DeviceStatus, AudioTopology, MixerState]:
        device = DeviceStatus(connected=True, usb_configuration=2, driver_bound=True)
        topology = AudioTopology(explicit_feedback=True)
        mixer = MixerState(direct_monitor_enabled=False)
        return device, topology, mixer

    def test_preflight_passes_only_with_all_physical_confirmations(self) -> None:
        device, topology, mixer = self.ready_inputs()
        state = evaluate_preflight(
            device,
            topology,
            mixer,
            [],
            speakers_disconnected=True,
            attenuation_confirmed=True,
            baseline_peak_dbfs=-80.0,
        )
        self.assertTrue(state.safe_for_playback)

    def test_unknown_direct_monitor_fails_closed(self) -> None:
        device, topology, mixer = self.ready_inputs()
        mixer.direct_monitor_enabled = None
        state = evaluate_preflight(
            device,
            topology,
            mixer,
            [],
            speakers_disconnected=True,
            attenuation_confirmed=True,
            baseline_peak_dbfs=-80.0,
        )
        self.assertFalse(state.safe_for_playback)
        self.assertIn("DSP direct monitoring", " ".join(state.refusal_reasons))

    def test_software_loop_fails(self) -> None:
        device, topology, mixer = self.ready_inputs()
        state = evaluate_preflight(device, topology, mixer, ["capture -> playback"])
        self.assertFalse(state.safe_for_playback)
        self.assertTrue(state.software_loopback_detected)

    def test_ramp_is_per_channel_and_bounded(self) -> None:
        self.assertEqual([-90.0, -85.0, -80.0, -75.0, -70.0, -65.0, -60.0], guarded_ramp_levels())
        plan = playback_channel_plan()
        self.assertEqual([1, 2, 3, 4], [item["channel"] for item in plan])
        self.assertEqual(4, len({item["tone_hz"] for item in plan}))

    def test_ramp_guard_aborts_on_level_or_growth(self) -> None:
        guard = RampGuard()
        self.assertIsNone(guard.observe(-70.0))
        self.assertIn("grew", guard.observe(-55.0) or "")
        guard = RampGuard()
        self.assertIn("reached", guard.observe(-17.9) or "")


if __name__ == "__main__":
    unittest.main()
