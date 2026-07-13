from __future__ import annotations

import unittest

from uh7000.models import EffectsState, MixerState, adcdac_preset, adc_preset


class ModelTests(unittest.TestCase):
    def test_default_mixer_has_eight_channels(self) -> None:
        mixer = MixerState()
        mixer.validate()
        self.assertEqual(8, len(mixer.channels))
        self.assertIsNone(mixer.direct_monitor_enabled)

    def test_invalid_pan_fails(self) -> None:
        mixer = MixerState()
        mixer.channels[0].pan = 16
        with self.assertRaises(ValueError):
            mixer.validate()

    def test_effect_rate_restrictions(self) -> None:
        effects = EffectsState(sample_rate=192000, dynamics_enabled=True)
        with self.assertRaises(ValueError):
            effects.validate()
        effects = EffectsState(sample_rate=96000, dynamics_enabled=True, reverb_enabled=True)
        with self.assertRaises(ValueError):
            effects.validate()

    def test_presets_are_deterministic(self) -> None:
        adc_mixer, _ = adc_preset()
        adcdac_mixer, _ = adcdac_preset()
        self.assertEqual("master", adc_mixer.line_output_source)
        self.assertEqual("digital-1-2", adcdac_mixer.line_output_source)
        self.assertTrue(
            all(
                channel.fader_db == -127.0
                for channel in adc_mixer.channels
                if channel.name.startswith("Computer")
            )
        )

    def test_json_state_converts_enums(self) -> None:
        payload = MixerState().to_dict()
        self.assertEqual("multitrack", payload["mode"])
        self.assertEqual("normal", payload["latency_profile"])


if __name__ == "__main__":
    unittest.main()
