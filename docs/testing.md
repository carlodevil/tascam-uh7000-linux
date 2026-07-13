# Feedback-Safe UH-7000 Test Flow

## Hardware-free checks

```sh
python3 -m compileall -q src tests tools
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m build
dpkg-buildpackage -us -uc -b
lintian ../tascam-uh7000-linux_*.deb
```

CI additionally launches the panel with `QT_QPA_PLATFORM=offscreen` when
PySide6 is available.

## Native Debian baseline

With speakers, headphones and physical output-to-input cables disconnected:

```sh
sudo uh7000ctl configure
uh7000ctl --json status
uh7000ctl --json topology
uh7000ctl --json diagnostics > uh7000-diagnostics.json
```

Expected topology:

- configuration 2;
- `snd_usb_audio` bound;
- 4 playback channels;
- 6 capture channels;
- `S24_3LE`;
- explicit endpoint `0x85`, not implicit feedback.

On 2026-07-13, the installed 0.2.0 beta package was validated on one
UH-7000: configuration 2, `snd_usb_audio`, 4 playback/6 capture channels, and
endpoint `0x85` were present. With all physical outputs disconnected, the
transactional clock-source test completed `automatic -> internal -> automatic`
with final selector `0x02`. This does not validate playback routing.

The separate configuration-1 backend was also validated through a physical
Left Line Output to Analog Input 2 loop. A generated 48 kHz stereo S24_3LE
1250 Hz stream returned at -1.75 dBFS, with the device restored to
configuration 2 afterwards. Do not use that test level with a raised input gain
or connected speakers/headphones.

## Configuration-1 analog playback

`uh7000-stream` is intentionally separate from the configuration-2 ALSA card.
It takes stereo S24_3LE raw PCM at exactly 48 kHz, uses the vendor stream for
the requested bounded duration, then returns the hardware to configuration 2.

With physical outputs disconnected, verify transport and recovery:

```sh
uh7000-stream --seconds 2 --execute
uh7000ctl --json topology
```

For a file, explicitly resample and pipe it into the backend:

```sh
ffmpeg -i input.wav -f s24le -ac 2 -ar 48000 - | \
  uh7000-stream --stdin --seconds 0 --execute
```

Record the pre/post `uh7000ctl --json topology` result, command exit status,
and any USB errors. Long-running playback and default PipeWire-sink integration
remain release gates.

## PipeWire-Pulse bridge

The optional per-user bridge creates a virtual `uh7000-analog` sink. It keeps
the hardware in configuration 1 only while enabled and returns it to
configuration 2 on disable:

```sh
uh7000-pipewire enable
pactl list short sinks | grep uh7000-analog
uh7000-pipewire disable
uh7000ctl --json topology
```

Use `uh7000-pipewire set-default` only after the enable/disable sequence is
clean. Capture the output of `systemctl --user status uh7000-stream.service`
and confirm configuration 2 plus `uh7000d` recovery after disable.

On 2026-07-13, beta3 completed a 60-second PipeWire-Pulse stream at 48 kHz
stereo while the control service was queried at 20, 40, and 60 seconds. Every
checkpoint reported configuration 1; the stream then stopped inactive without
failure and the device returned to configuration 2. This is a bounded handoff
check, not the required 30-minute or eight-hour endurance evidence.

Beta4 additionally read endpoint `0x85` during a five-second configuration-1
run. The feedback averaged 47.994379 frames/ms (range 47.977112 to 48.0), and
the adaptive packet scheduler transmitted 47.994205 frames/ms. This prevents
the fixed-48-frame drift that would otherwise accumulate in long playback.

The same beta4 validation manually selected configuration 1, confirmed that
`uh7000ctl` still reported the device, then ran the packaged
`tascam-uh7000-configure 1-5` helper. It selected configuration 2, registered
`snd_usb_audio`, restored the UH-7000 ALSA card, and the restarted D-Bus
service reported configuration 2. This covers a software configuration
handoff, not a physical USB unplug or power-cycle.

## Clock-source control

With all physical outputs still disconnected, the persistent control path is:

```sh
uh7000ctl --json clock-source internal --outputs-disconnected --execute
uh7000ctl --json clock-source automatic --outputs-disconnected --execute
```

The D-Bus service exposes the same operation as `SetClockSource(source,
outputs_disconnected)`. It reads the prior selector, verifies the requested
value, and restores the prior selector when a write or readback fails.

Record at least ten seconds of silence from all six lanes before any playback.
Clipping with all outputs physically disconnected is an input/hardware problem
and blocks output tests.

## Passthrough isolation

Before every playback attempt:

1. Stop DAWs, browser capture and prior test processes.
2. Inspect `pw-link -l` and remove every capture-to-playback or loopback link.
3. Read the UH-7000 DSP monitor state and confirm it is off. Unknown is not off.
4. Set physical inputs to line level and minimum gain.
5. Disconnect speakers and headphones.
6. Use an independent capture interface when available. Otherwise install
   physical attenuation before a same-device loop.
7. Measure a new capture baseline.

Evaluate the software gates:

```sh
uh7000ctl --json preflight \
  --speakers-disconnected \
  --attenuated-loopback \
  --baseline-peak-dbfs -80
```

The command must remain nonzero while direct-monitor readback is unavailable.
Do not bypass this gate with a manual `aplay` command.

## Guarded channel test

Once direct-monitor readback is implemented and preflight passes:

- open capture before playback;
- test one playback channel at a time;
- use 1250, 1500, 1750 and 2000 Hz for channels 1–4;
- ramp each channel from -90 to -60 dBFS in 5 dB steps;
- evaluate capture every 100 ms;
- abort at -18 dBFS, any clipped sample, or growth greater than 12 dB per
  guard window;
- stop after three seconds per channel; and
- confirm no tone appears on an unintended channel.

Never test channel order by putting the same tone on all channels.

## Matrix and endurance

Run channel mapping and duplex checks at 44.1, 48, 88.2, 96, 176.4 and
192 kHz. Run 30 minutes at every rate, then eight-hour duplex tests at 48, 96
and 192 kHz. Record XRUNs, USB errors, packet/feedback status, drift, CPU load,
and PipeWire graph state.

Also test reconnect, device power cycle, service restart, UI restart,
suspend/resume, invalid AES/EBU clock, unplug during read, and unplug during a
transactional control write.

## Control promotion

Mixer/effect controls stay disabled until the capture/readback procedure in
`protocol.md` passes. A beta release cannot be marked stable until every
enabled control has a repeatable hardware test and two additional UH-7000
systems confirm duplex operation.
