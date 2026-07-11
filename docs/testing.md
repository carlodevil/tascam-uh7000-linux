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
