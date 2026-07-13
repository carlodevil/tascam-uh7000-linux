# UH-7000 Windows control baseline — 2026-07-13

This is the feedback-safe Windows handoff for the Debian implementation. During
every capture, speakers, headphones, and loopback cables were disconnected. No
playback stream was opened. Reversible controls were changed in isolation and
returned to the state shown by the panel before capture.

The source device reported driver 1.02, firmware 1.08, USB 2.0, 24-bit/48 kHz,
multitrack mode, automatic clock, and no valid digital input signal.

## Artifacts

```text
effects-and-memory-controls.tar.gz  66096938  f56c7aca7a107cbffd110063bb96ae1844dfb0a2f7da6e43d4916024ab20670f
interface-controls.tar.gz           71804615  82e51354adfcec78c4412cf3f97d381c75ab19298366bc79f64f3e925c14ca6b
manifest.json                          75974  158274669f8c290617b6a9f48d38b29ce8c332981decb2e538ea0e789c55be1c
mixer-controls.tar.gz               88694971  3d6f2f599e325c8c53b34baf1bcfed829e5c9e439ec8265f699b998ea4c500a3
direct-monitor-readback-artifacts.tar.gz 16978087  9476d5a9f17b4bae2e119678d1fa0bde365a9b8f6a93a148b9eef9e6988bfe92
windows-completion/windows-completion-mixer.tar.gz 19639006  0b902609a7c27e3d1301a7bce0d9ceac2e7151b83b4869dbf2bbb0087697c31b
windows-completion/windows-completion-presets-resets.tar.gz 33436343  8e102d4e16460efbc38ed34048717a12a8f5d2d159c38850d4a2a497b0de580b
```

`manifest.json` contains the SHA-256, size, and decoded vendor requests for
every raw capture. Regenerate it with:

```sh
python3 tools/build_windows_capture_manifest.py CAPTURE_DIRECTORY manifest.json
```

## Exact actions

| Area | Capture | Action and rollback | Result |
| --- | --- | --- | --- |
| Interface | `audio-performance.pcap` | selected highest, high, normal, low, and lowest latency; restored high | no device vendor request; this is a Windows-driver setting and maps to a Linux host latency profile |
| Interface | `auto-power-save.pcap` | 30 min → off → 30 min | paired `0x54` writes |
| Interface | `link-line-button.pcap` | enabled → disabled → enabled | paired `0x54` writes |
| Interface | `analog-input-source.pcap` | MIC → LINE → MIC | paired `0x54` writes |
| Interface | `line-output-routes.pcap` | selected all five routes independently; restored Master L/R | five `0x4d` state images |
| Interface | `digital-output-routes.pcap` | selected all five routes independently; restored Master L/R | five `0x4d` state images |
| Interface | `digital-output-format.pcap` | S/PDIF → AES/EBU → S/PDIF | complete `0x41`/`0x54` transaction sequences |
| Mixer | analog/digital solo and mute captures | enabled once, then disabled | paired `0x4d` images where listed in the manifest |
| Mixer | analog/digital pre/post captures | changed once, then restored | `0x4d` images; `analog-pre-post` has only one captured edge |
| Mixer | `computer-solo.pcap` | enabled once, then disabled | paired `0x4d` images |
| Mixer | computer mute captures | enabled once, then disabled | USBPcap startup missed edges; retain as incomplete evidence, not production mappings |
| Mixer | `monitor-mix.pcap` | center/input position → computer side → original position | paired `0x54` writes, values `0x523d` and `0x247b`, index `0x012c` |
| Mixer | `direct-monitor-readback/` follow-up | panel restart, isolated MON MIX transition, restore to Computer, physical USB reconnect | Computer/off is `0x54` value `0x7f60`, index `0x012c`; Windows reasserts it on reconnect without readback |
| Mixer | fader, pan, send, and return captures | one wheel detent, then inverse detent | captured `0x4d` deltas; no value was intentionally left changed |
| Effects | each named effect capture | effect on, then off | request `0x42`, 256-byte DSP image |
| Effects | `effects-parameters.pcap` | one detent and inverse detent on every visible knob; selected every reverb model; restored Studio, 24 ms, 1.4 s | request `0x42` DSP images |
| Memory | `presets-save-reset.pcap` | File → Save, confirmation accepted, success acknowledged | request `0x55` four-block read/write sequence plus configuration refresh |

Effect Reset, Mixer Reset, ADC Preset, and ADC/DAC Preset were subsequently
captured in a dedicated, feedback-safe completion pass. See
`windows-completion/README.md`, its manifest, and the two compressed artifact
archives. The panel state was restored manually after every destructive action.
These captures document Windows behavior but do not remove the production gate:
Linux must still provide atomic state rollback before exposing reset or preset
writes.

## Interpretation gates

- `0x42`, `0x4d`, `0x54`, and `0x55` remain research-only writes. The captures
  prove Windows behavior, not safe Linux write/readback semantics.
- Empty captures are meaningful only where this document says the control is
  host-local or disabled. Never synthesize a hardware command from an empty
  capture.
- `audio-performance` belongs in PipeWire/ALSA latency configuration, not the
  USB protocol module.
- Repeated Computer 1/2, 3, and 4 mute captures contain no vendor request and
  are classified as Windows-host mixing behavior. The isolated Computer
  POST-to-PRE edge emits `0x4d`; PRE-to-POST emits no vendor request, so the
  hardware mapping remains research-only.
- The existing atomic `0x49` clock primitive remains the only write with
  immediate symmetric hardware readback and rollback.
