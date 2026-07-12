# UH-7000 Windows captures — 2026-07-12

Outputs, headphones and loopback cables were disconnected. Each setting was
changed alone and restored in the official Mixer Panel. Raw captures are in
`uh7000-control-captures.tar.gz`.

## SHA-256

```text
baseline.pcap 9f02dec75832fd847e5c11c3b8e60a787c9562956f319afbd8bdfa566e510cae
clock-source.pcap 501b7248026c0044a24f3864fc51907fc535ec065ced3230e8b0cba6eb478185
computer-playback-route.pcap 042de7fe8366391335bd6f7a38a0a1563ba93e9d8a2deba306a6f8f0d63932a6
direct-monitor.pcap 646e4fcaed013f883cff1b794e1da1bd8faf464024e938ab36963df64a9f4cd6
line-output-source.pcap a9f0dcaca842dc1430fb35f8d9ed5ceefbea2f171100453deaa451a8dd3a5569
mixer-mode.pcap bf7f8972159b59e21bd75fd911da863caa13e2db58bb638a013d37d41ef16511
uh7000-control-captures.tar.gz fbe8e7e7434e357e0e48a9c6e41b74dc7609ea1a7d44c5571e7cc640f34cb779
```

## Verified delta

Clock source is the only bounded write with immediate symmetric readback:

```text
automatic read: c0 49 00 00 00 00 01 00 -> 02
select internal: 40 49 00 00 00 00 00 00
internal read:   c0 49 00 00 00 00 01 00 -> 00
select automatic:40 49 02 00 00 00 00 00
automatic read: c0 49 00 00 00 00 01 00 -> 02
```

Mixer and routing changes write request `0x4d` with a 64-byte state image.
The interrupt stream on endpoint `0x83` did not provide a corresponding state
readback. Mixer Mode also writes `0x54` and reconfigures the USB device. Those
requests remain research-only.

The production protocol contains an atomic `0x49` primitive with readback and
rollback, but it is not exposed through D-Bus, CLI or UI until an
output-disconnected Linux hardware test passes.

Normalized Linux-ready fixtures are in
`research/windows-control-fixtures.json`. Each control is explicitly marked
as verified, candidate, or incomplete. `tools/validate_control_fixtures.py`
checks image lengths, byte-delta offsets, schema version and the global
write-disabled safety gate.
