# Windows completion capture pass

This follow-up closes the Windows-side gaps identified after the original
2026-07-13 baseline. The physical analog loopback was disconnected, no playback
stream was active, and the UH-7000 direct-monitor control was kept at
`Computer` (off). Analog input 2 was never raised manually. Destructive preset
and reset actions were performed one at a time and the known-safe baseline was
restored after every action.

Source system: Windows driver 1.02, firmware 1.08, USB 2.0, 24-bit/48 kHz.
The capture-time device address was 6 unless a preset caused re-enumeration.

## Artifacts

The raw USBPcap files are split into two compressed archives to remain below
GitHub's single-file limit:

- `windows-completion-mixer.tar.gz`: Computer mute and isolated Computer
  PRE/POST captures.
- `windows-completion-presets-resets.tar.gz`: Effect Reset, Mixer Reset, ADC
  Preset, and ADC/DAC Preset captures.
- `manifest.json`: SHA-256, raw size, and decoded vendor requests for every
  capture.

```text
windows-completion-mixer.tar.gz          19639006  0b902609a7c27e3d1301a7bce0d9ceac2e7151b83b4869dbf2bbb0087697c31b
windows-completion-presets-resets.tar.gz 33436343  8e102d4e16460efbc38ed34048717a12a8f5d2d159c38850d4a2a497b0de580b
manifest.json                                7924  db625cd03f2c08b97f219ae374fc5e7ed08cc8df0d48febc72d401b90b464096
```

## Exact results

| Capture | Isolated action | USB result |
| --- | --- | --- |
| `computer-mute.pcap` | Computer 1-2 mute on/off, with long waits | no vendor request |
| `computer-3-mute.pcap` | Computer 3 mute on/off | no vendor request |
| `computer-4-mute.pcap` | Computer 4 mute on/off | no vendor request |
| `computer-pre-post.pcap` | combined POST/PRE experiment | one `0x4d` image; retained only as historical corroboration |
| `computer-pre.pcap` | Stereo Mix Computer POST -> PRE | one `0x4d`, 64-byte image |
| `computer-post.pcap` | Stereo Mix Computer PRE -> POST | no vendor request after 15 seconds |
| `effect-reset.pcap` | Compressor threshold changed to -11 dB, then File -> Effect Reset | `0x4d` 64-byte mixer image and `0x42` 256-byte DSP image |
| `mixer-reset.pcap` | File -> Mixer Reset | `0x54` value `0x3fbf`, index `0x012c`; one `0x4d`; two `0x42` images |
| `adc-preset.pcap` | File -> ADC Preset, confirmation accepted | standard USB re-enumeration traffic, descriptor reads, and `SET_CONFIGURATION 1`; no vendor request |
| `adc-dac-preset.pcap` | File -> ADC/DAC Preset, confirmation accepted | one `0x4d` image and two `0x42` images |

The empty Computer mute captures were repeated deliberately. Treat those mute
controls as Windows-host mixing behavior and implement them in PipeWire, not as
UH-7000 vendor writes. The asymmetric Computer PRE/POST pair must also remain
research-only until Linux can prove the reverse state from a full device image
or an independent readback. Never synthesize a command from an empty capture.

## Observed preset states

`ADC Preset` reset direct monitoring toward Input, set both analog sources to
MIC, set all input PRE/POST selectors to POST, set channel faders to 0 dB, set
line output to Master L/R, set digital output to Analog 1/2, and disabled the
reverb engine/send.

`ADC/DAC Preset` reset direct monitoring toward Input, retained LINE analog
sources, set all PRE/POST selectors to POST, set all channel faders to 0 dB,
set line output to Digital 1/2, set digital output to Analog 1/2, and disabled
the reverb engine/send.

`Effect Reset` restored Compressor to -12 dB, 2.0:1, 20 ms attack, 420 ms
release, +4 dB gain, off; it selected Hall reverb, 42 ms pre-delay, 2.7 s time.

`Mixer Reset` moved direct monitoring to the midpoint, unlinked Computer 1/2,
set channel faders to 0 dB, selected POST, disabled the reverb send, selected
line output Master L/R, and selected digital output Computer 1/2.

## Final restored state

The panel was left in Multitrack mode with direct monitoring at Computer/off,
Analog 1/2 set to LINE and muted at minimum, Analog 1 and Digital 1 PRE,
Analog 2 and Digital 2 POST, Computer 1/2 linked at -0.20 dB, line output
Computer 1/2, digital output Master L/R, S/PDIF, send reverb enabled, and the
Studio 24 ms / 1.4 s reverb engine on. Compressor remained off at the values
listed above.
