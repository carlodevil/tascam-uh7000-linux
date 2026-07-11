from __future__ import annotations

import unittest

from uh7000.audio import find_alsa_card, parse_stream_topology


STREAM = """TASCAM UH-7000 at usb-xhci, high speed
Playback:
  Status: Stop
  Interface 1
    Altset 1
    Format: S24_3LE
    Channels: 4
    Rates: 44100, 48000, 88200, 96000, 176400, 192000
    Sync Endpoint: 0x85 (1 IN)
    Implicit Feedback Mode: No
Capture:
  Status: Stop
  Interface 2
    Altset 1
    Format: S24_3LE
    Channels: 6
    Rates: 44100, 48000, 88200, 96000, 176400, 192000
"""


class AudioTests(unittest.TestCase):
    def test_card_name(self) -> None:
        self.assertEqual("UH7000", find_alsa_card(" 2 [UH7000 ]: USB-Audio - TASCAM UH-7000"))

    def test_stream_topology(self) -> None:
        topology = parse_stream_topology(STREAM)
        self.assertEqual(4, topology.playback_channels)
        self.assertEqual(6, topology.capture_channels)
        self.assertEqual("S24_3LE", topology.sample_format)
        self.assertTrue(topology.explicit_feedback)
        self.assertEqual(192000, topology.sample_rates[-1])

    def test_implicit_feedback_is_rejected(self) -> None:
        topology = parse_stream_topology(
            STREAM.replace("Implicit Feedback Mode: No", "Implicit Feedback Mode: Yes")
        )
        self.assertFalse(topology.explicit_feedback)


if __name__ == "__main__":
    unittest.main()
