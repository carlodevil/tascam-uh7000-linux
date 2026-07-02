# UH-7000 Test Flow

This document defines the supported test sequence for the Linux package. It is
written to keep unsafe output-routing experiments separated from read-only or
capture-only checks.

## Baseline Install Check

After installing the package and reconnecting the UH-7000:

```sh
uh7000ctl status
sudo uh7000ctl control-status
sudo uh7000ctl state-dump /tmp
sudo uh7000ctl report 1 > uh7000-report.json
```

Expected baseline:

- USB configuration is `2`.
- Interfaces `2.0`, `2.1`, and `2.2` are bound to `snd-usb-audio`.
- ALSA shows the `UH7000` card.
- Playback exposes 4-channel `S24_3LE`.
- Capture exposes 6-channel `S24_3LE`.
- Playback reports sync endpoint `0x85` and `Implicit Feedback Mode: No`.
- Vendor selector request `0x49` responds.
- Read-only state dump request `0x55` returns 512-byte pages for `0x1f00` and
  the direct Windows `0xf800` image pages `0x007c..0x007f`.

`state-dump` writes a raw 512-byte page and JSON metadata. It does not play
audio, does not send mixer writes, and does not scan page indices. Local
hardware rejected page `0x0002` in the current Linux state, so that page is not
an installed default.

## Capture Gate

Before any playback or output-routing test:

```sh
sudo uh7000ctl preflight 2
```

`preflight` must pass. It does not play audio and does not send mixer writes.
If it fails because capture clips, do not run output tests.
If it fails because playback is in implicit-feedback mode, the output test is
not a valid routing check. Stop USB audio clients and reload the USB audio
module for this test session:

```sh
sudo modprobe -r snd_usb_audio
sudo modprobe snd_usb_audio implicit_fb=N ignore_ctl_error=Y skip_validation=Y
sudo uh7000ctl configure
```

The module reload affects USB audio devices globally until another reload or
reboot. The package records this as a test precondition because local usbmon
captures showed correct 48 kHz packet sizing only when the UH-7000 explicit
feedback endpoint `0x85` was active. Explicit feedback alone has not restored
analog output, so it is a necessary gate, not the final routing fix.

When the front-panel meter is solid red or the report has
`"safe_for_output_test": false`, disconnect any output-to-input loopback,
power-cycle the UH-7000, reconnect USB, and repeat `preflight`.

## Output Loopback Test

Only after `preflight` passes:

1. Connect the UH-7000 outputs to the inputs with gain set low.
2. Run:

```sh
sudo uh7000ctl loopback-test 3 -60
```

The loopback test plays a 1 kHz, -60 dBFS, 4-channel `S24_3LE` tone and records
the 6-channel capture stream. It fails if capture clips or if no 1 kHz return
tone appears above -90 dBFS.

## Recovery

For the constant clipped-output state observed on local hardware, use the
0x4d-only noise suppression gate:

```sh
sudo uh7000ctl suppress-noise 2
```

This command does not play audio and does not send request `0x42`. It applies a
Windows-derived `0x4d` block that zeroes one channel-0 gain word, then checks
capture again. On local hardware it reduced the looped-back output from hard
clipping to roughly the input noise floor (`-96 dBFS RMS` on the connected
lanes). It also muted the return tone in `loopback-test`, so it is a recovery
gate, not the final output-routing fix.

The low-level installed vendor-write recovery command is:

```sh
sudo uh7000ctl quiet
```

It sends zeroed payloads for verified requests `0x4d` and `0x42`. If clipping
persists after `quiet`, stop live testing and power-cycle the interface.

For a repeatable before/after recovery attempt, use:

```sh
sudo uh7000ctl recover 1
```

`recover` does not play audio and does not send experimental payloads. It checks
capture, applies the same verified `quiet` blocks, waits briefly, and checks
capture again. If it still fails, disconnect the output-to-input loopback,
power-cycle the UH-7000, reconnect USB, and run `sudo uh7000ctl preflight 2`.

`capture-health` and `report` classify clipped input states:

- `odd-input-mirror`: channels 1/3/5 clip.
- `even-input-mirror`: channels 2/4/6 clip.
- `all-channels`: all six USB capture channels clip.
- `partial`: another clipped-channel pattern.

Any clipped pattern keeps output playback gated.

## Analog Output Noise On Power-Up

If the UH-7000 outputs emit steady noise immediately after power-on or USB
attach, before running manual `uh7000ctl quiet`, `recover`, or output tests, do
not keep the output-to-input loopback connected. The package hotplug service
only selects USB configuration `2` and registers `snd-usb-audio`; it does not
send vendor mixer requests `0x4d` or `0x42`.

Use this isolation sequence:

1. Disconnect any output-to-input loopback.
2. Power-cycle the UH-7000 and reconnect USB.
3. Run `sudo uh7000ctl preflight 2`.
4. If preflight is clean with outputs disconnected, the input path is usable and
   the remaining issue is output-side noise/routing.
5. Reconnect loopback only for `sudo uh7000ctl loopback-test 3 -60`, and only
   after preflight passes.

If preflight still clips with outputs disconnected, treat it as an input-side or
hardware baseline problem and do not run output tests.

To characterize noise visible at the inputs without generating host playback,
run:

```sh
sudo uh7000ctl input-noise 4
```

This capture-only analyzer reports RMS/peak, DC offset, clip polarity,
zero-crossing rate, strongest spectral bins, and coarse band power for all six
USB capture channels. If the outputs are patched to the inputs, it describes the
noise currently returning through that loopback.

## Waiting For Manual Recovery

When manual power-cycling is needed, use `wait-clean` to poll the safe preflight
gate without playback or mixer writes:

```sh
sudo uh7000ctl wait-clean 12 1 10 carlodevelopmentwork
```

The arguments are: retry count, capture seconds per retry, interval seconds,
and optional ntfy.sh topic. The command sends at most one notification and
returns only when `preflight` passes. If all retries fail, output playback
remains gated.

## Offline Control-Plane Images

The decoded 0xf800 mixer/UI image path can be inspected without writing to the
UH-7000:

```sh
uh7000ctl control-plan f800
/tmp/uh7000-emuv/bin/python tools/uh7000_cpl_emulate.py --f800-image --json
```

This documents the six rate-specific `0x42` blocks, the current `0x4d` block at
image offset `0x600`, the footer checksum, and request `0x55` pages
`0x007c..0x007f`. It is not a live write test. The package does not upload the
0xf800 image automatically while the image semantics and recovery path are
being proven.

The live write path is available only as an explicit experiment:

```sh
UH7000_EXPERIMENTAL_0X55_WRITE=1 sudo -E uh7000ctl f800-upload /tmp/uh7000-f800.bin
```

`f800-upload` runs preflight first, saves the current `0x007c..0x007f` pages to
a backup under `/tmp`, verifies every page by readback, and restores the backup
if capture clips immediately after upload. If manual rollback is needed:

```sh
UH7000_EXPERIMENTAL_0X55_WRITE=1 sudo -E uh7000ctl f800-restore /tmp/uh7000-f800-backup.xxxxxx.bin
```

## Issue Reports

Attach this output to GitHub issues:

```sh
sudo uh7000ctl report 1 > uh7000-report.json
```

The report format is described by `report-schema.json`.
