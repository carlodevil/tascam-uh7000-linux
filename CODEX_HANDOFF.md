# Codex Handoff: TASCAM UH-7000 Linux

## Windows follow-up completed 2026-07-12

The isolated Windows capture task below has been completed and committed on
`agent/rebuild-uh7000-linux`. Evidence, hashes and decoded deltas are under
`research/windows-captures/2026-07-12/`. Request `0x49` clock values have
symmetric readback; an atomic, rollback-capable primitive was added but remains
unexposed pending the output-disconnected Linux hardware test. Requests `0x4d`
and `0x54` remain research-only because no state readback was observed.

## Objective

Finish the TASCAM UH-7000 Linux solution: reliable hotplug and device access,
a verified control plane, safe/correct playback and capture routing, and a
releasable Debian package with documented installation and validation.

## Repository

- Windows checkout: `C:\Users\carlo\OneDrive\Documents\TASCAM Driver`
- Remote: `https://github.com/carlodevil/tascam-uh7000-linux.git`
- Branch: `agent/rebuild-uh7000-linux`
- Base commit at handoff: `55071f6 Recreate Debian artifact directory after build`
- Linux checkout: `/home/carlo/Projects/tascam-uh7000-linux`

The Windows checkout was clean when this file was written. The Linux checkout
has the uncommitted changes listed below; do not assume they are present here
until they have been deliberately committed and pushed.

## Completed and verified on Linux

- Installed package: `tascam-uh7000-linux 0.2.0~beta1`.
- UH-7000 `0644:8048` is in USB configuration 2 with stock `snd_usb_audio`
  bound.
- ALSA topology is confirmed as 4 playback / 6 capture, `S24_3LE`, 48 kHz
  supported, explicit feedback endpoint `0x85` and no implicit feedback.
- User-space vendor reads work without sudo after the udev fix:
  selector request `0x49` returns `0x02`.
- Vendor status interface 3 is unclaimed by a kernel driver. A read-only bulk
  read from endpoint `0x83` repeatedly returns framed packets such as
  `0b b0 6b 00`, `0b b0 6c 00`, and periodic `0x66/0x67/0x68` packets.
- A three-second six-channel capture baseline was clean: about `-92 dBFS RMS`
  and no clipping.
- `uh7000d` D-Bus user service is active.

## Linux changes not yet committed

1. `udev/90-tascam-uh7000.rules`
   - Adds `GROUP="audio", MODE="0660"` alongside `TAG+="uaccess"`.
   - This makes control access work immediately for normal Debian desktop
     users in the `audio` group, including devices attached before install.
2. `debian/tascam-uh7000-linux.postinst`
   - Replays a synthetic udev `add` event after rule reload so an already
     connected device receives the rule.
3. `src/uh7000/protocol.py`, `device.py`, `controller.py`, and tests
   - Add strict read-only parsing/reporting of vendor endpoint `0x83` status
     packets. No vendor write was added.
4. `docs/windows-usb-capture.md`, release checklist and Debian docs manifest
   - Define the controlled Windows USBPcap capture process below.
5. `scripts/ci-smoke.sh`
   - Asserts the udev/install behavior remains packaged.

Linux validation passed after these changes:

```text
26 unit/smoke tests passed
Debian package build passed
Installed package diagnostics showed selector_status=2 and vendor status
packets {control: 107, value: 0}, {control: 108, value: 0}
```

## Critical safety boundary

Do not promote or brute-force vendor writes. Earlier requests `0x42`, `0x4d`
and `0x55` candidates can create hard clipping and have not established stable
output routing. The existing Linux control panel correctly disables unverified
mixer/effect writes.

The physical UH-7000 does not provide a direct-monitor switch. Mixer and
output routing are computer Mixer Panel settings. Correct output support
requires Windows USB evidence for isolated setting changes.

## Windows task: capture control traffic

Read `docs/windows-usb-capture.md` in this repository. In short:

1. Disconnect speakers, headphones and all output-to-input loopback cables.
2. Install USBPcap and Wireshark if needed, then start an unfiltered capture
   on the controller hosting the UH-7000.
3. Record ten seconds of idle Mixer Panel traffic as `baseline`.
4. Change exactly one setting at a time, Apply/Save, wait five seconds, then
   restore it. Capture separately:
   - Mixer mode;
   - direct-monitor channel state;
   - line-output source;
   - computer playback route;
   - Automatic to Internal clock source, only if no AES/EBU clock is active.
5. Preserve the `.pcapng`, a timestamped text log, before/after screenshots,
   and firmware/driver/Windows versions.

The next Codex instance should parse each baseline-to-change delta, identify
the bounded USB transfer and payload, and only then implement a Linux write
with readback, rollback and an output-disconnected hardware test.

## Current limitation

No live Windows Codex/chat session can be started or controlled from Linux.
This document is the handoff point. Do not reboot the Linux session expecting
its active chat to follow Windows.
