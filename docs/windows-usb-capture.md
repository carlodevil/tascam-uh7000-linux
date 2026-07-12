# Windows USB Control Capture

Capture one Mixer Panel change per file with speakers, headphones and physical
output-to-input loops disconnected. Record an idle baseline first. Wait at
least five seconds after the change, restore the original value, and wait
again before stopping capture.

The 2026-07-12 session used USBPcap 1.5.4.0 on `\\.\USBPcap2`. The UH-7000
reported driver 1.02, firmware 1.08, USB 2.0, 24-bit/48 kHz, Multitrack mode,
automatic clock with internal selected, and no valid digital input.

Captured transitions:

| File | Isolated transition |
| --- | --- |
| `baseline.pcap` | ten seconds idle |
| `mixer-mode.pcap` | Multitrack → Stereo Mix → Multitrack |
| `clock-source.pcap` | automatic → internal → automatic |
| `direct-monitor.pcap` | Analog 1 MUTE off → on → off |
| `line-output-source.pcap` | Master L/R → Analog in 1/2 → Master L/R |
| `computer-playback-route.pcap` | Computer 1–2 MUTE off → on → off |

Run `tools/parse_usbpcap.py` against the extracted archive to reproduce the
vendor-control summary. Do not replay `0x4d` or `0x54` payloads: they are full
state images and have no verified readback on firmware 1.08.
