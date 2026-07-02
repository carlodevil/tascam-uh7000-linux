# TASCAM UH-7000 Linux Support

Debian package for the TASCAM UH-7000 USB audio interface.

The UH-7000 powers up in a vendor-specific USB configuration. The same device
also exposes a USB Audio 2.0 configuration. This package switches the device to
that USB Audio 2.0 configuration on hotplug and registers the device ID with
the standard `snd_usb_audio` driver.

## Status

Early hardware support package. USB configuration, driver binding, ALSA stream
exposure, and analog capture work locally. Verified vendor mixer recovery
commands are included to clear capture/output overload states observed during
loopback testing.
The full vendor mixer/control plane is still under active reverse engineering,
and physical analog output may remain muted or unrouted until that work is
complete.
Current output-loopback experiments require ALSA to use the UH-7000 explicit
feedback endpoint (`0x85`, `Implicit Feedback Mode: No`). `uh7000ctl preflight`
and `uh7000ctl report` now surface that state because valid ALSA playback
opening is not enough to prove that the device will route samples to the analog
outputs.

Known local findings:

- USB ID: `0644:8048`
- Manufacturer/product strings: `TASCAM` / `UH-7000`
- Default Linux-visible configuration: `1`, vendor-specific
- USB Audio 2.0 configuration: `2`
- Configuration `2` advertises 24-bit PCM, 4 output channels, and 6 input channels
- Configuration `2` does not expose the full UH-7000 mixer panel through normal
  ALSA mixer controls

This project does not include TASCAM/Ploytec Windows driver binaries.

## Build

```sh
scripts/build-deb.sh
```

The package is written to `dist/`.

Run the hardware-free smoke test used by CI:

```sh
make test
```

## Install

```sh
sudo dpkg -i dist/tascam-uh7000-linux_0.1.33-1_all.deb
```

Unplug and replug the UH-7000, then check:

```sh
uh7000ctl status
sudo uh7000ctl control-status
sudo uh7000ctl state-dump /tmp
uh7000ctl control-plan adcdac
uh7000ctl control-plan routes
uh7000ctl control-plan f800
uh7000ctl control-plan noise-mute
sudo uh7000ctl preflight
sudo uh7000ctl loopback-test
sudo uh7000ctl report
sudo uh7000ctl suppress-noise 2
sudo uh7000ctl recover
sudo uh7000ctl wait-clean 12 1 10 carlodevelopmentwork
uh7000ctl input-noise 4
uh7000ctl capture-health
aplay -l
arecord -l
```

If the device is already plugged in, you can manually trigger configuration:

```sh
sudo uh7000ctl configure
```

If the UH-7000 emits constant clipped output noise into a looped input, apply
the 0x4d-only recovery gate:

```sh
sudo uh7000ctl suppress-noise 2
```

This does not play audio and does not send request `0x42`. It is a
noise-suppression recovery gate, not proof that playback routing is fixed.

If the UH-7000 input meter or USB capture path is overloaded after routing
tests, clear the verified vendor mixer blocks:

```sh
sudo uh7000ctl quiet
```

Then verify that USB capture is no longer clipping:

```sh
uh7000ctl capture-health
```

For a single no-playback before/after recovery sequence:

```sh
sudo uh7000ctl recover 1
```

To wait for a clean capture baseline after manual power-cycling, optionally
notifying an ntfy.sh topic once if manual action is still required:

```sh
sudo uh7000ctl wait-clean 12 1 10 carlodevelopmentwork
```

To characterize input-visible noise without playback or mixer writes:

```sh
uh7000ctl input-noise 4
```

`capture-health` records a short 48 kHz, 6-channel `S24_3LE` sample from
`hw:UH7000,0`, prints per-channel peak/RMS/clipping counts, and exits nonzero
if any channel hits full scale. It also classifies clipped-channel patterns so
`odd-input-mirror`, `even-input-mirror`, `all-channels`, and `partial` failure
states can be compared between reports.

## Uninstall

```sh
sudo dpkg -r tascam-uh7000-linux
```

## How It Works

The package installs:

- A udev rule for USB ID `0644:8048`
- AppStream metainfo that advertises the UH-7000 USB modalias
- Bash completion for `uh7000ctl`
- A systemd oneshot service for hotplug handling
- A root-only helper that writes `2` to the device's `bConfigurationValue`
- A `snd_usb_audio` `new_id` registration for `0644:8048`
- `uh7000ctl`, a diagnostic CLI
- `uh7000ctl(1)`, an installed manual page for the diagnostic CLI
- `testing.md` and `report-schema.json` under the installed package docs
- `release-checklist.md` under the installed package docs
- `control-plan-matrix.md` and `control-plan-matrix.json` under the installed
  package docs for offline CPL routing/effect candidate evidence
- `uh7000ctl control-status`, which performs a read-only vendor selector
  request (`0x49`) so the vendor control plane can be inspected without
  modifying device state
- `uh7000ctl state-dump`, which performs the verified read-only request `0x55`
  transfers and writes raw 512-byte state pages plus JSON metadata for
  reverse-engineering comparisons. It reads the populated live fingerprint page
  `0x1f00` and the directly decoded `0xf800` image pages `0x007c..0x007f`.
- `uh7000ctl control-plan`, which prints decoded dry-run request payloads for
  known mixer plans without sending USB controls
- `uh7000ctl control-plan f800`, which documents the decoded Windows 0xf800
  mixer/UI image wrapper, layout, checksum, and request `0x55` page mapping
  without uploading anything to hardware
- `uh7000ctl f800-upload`, which experimentally writes a user-supplied
  2048-byte 0xf800 image to request `0x55` pages `0x007c..0x007f` only when
  `UH7000_EXPERIMENTAL_0X55_WRITE=1` is set. It runs preflight first, saves a
  backup, verifies readback, and rolls back if capture clips immediately after
  upload.
- `uh7000ctl f800-restore`, which writes a saved 0xf800 backup image back to
  request `0x55` pages for manual rollback.
- `uh7000ctl suppress-noise`, which applies a Windows-derived 0x4d-only
  recovery block and checks capture before/after
- `uh7000ctl preflight`, which checks USB configuration, `snd_usb_audio`
  binding, ALSA playback/capture stream shape, explicit feedback mode, vendor
  control status, and capture clipping before any output-routing experiment
- `uh7000ctl loopback-test`, which first runs `preflight`, then plays a low
  1 kHz tone and measures the return tone in USB capture for output-routing
  verification
- `uh7000ctl report`, which prints a JSON diagnostic report suitable for
  attaching to GitHub issues or release notes, including parsed playback
  feedback state
- `uh7000ctl quiet`, which sends the verified vendor requests `0x4d` and `0x42`
  with zeroed mixer payloads to clear the observed USB-side overload state
- `uh7000ctl recover`, which runs capture-health before and after the same
  verified quiet recovery blocks and fails if capture remains clipped
- `uh7000ctl wait-clean`, which polls the no-playback preflight gate and can
  send one ntfy.sh manual-action notification while waiting for a clean baseline
- `uh7000ctl input-noise`, which captures input only and reports clipped noise
  levels, DC offset, strongest spectral bins, and coarse band power
- `uh7000ctl capture-health`, which gives a repeatable pass/fail check for
  clipped USB capture samples

After configuration `2` is selected, Linux should probe the USB Audio 2.0
interfaces through `snd_usb_audio`.

## Troubleshooting

Show package/device status:

```sh
uh7000ctl status
```

Manually reconfigure:

```sh
sudo uh7000ctl configure
```

Check service logs:

```sh
journalctl -u 'tascam-uh7000-configure@*'
```

If ALSA still does not show the device after configuration `2` is active, the
next implementation step is an ALSA quirk or optional DKMS package.

Avoid forcing configuration `1` through `snd_usb_audio`; local testing showed
that path can wedge the USB device until a power-cycle/replug.

For output-loopback tests, check the playback feedback mode:

```sh
sudo uh7000ctl preflight 2
```

The expected state is sync endpoint `0x85` with `Implicit Feedback Mode: No`.
If preflight reports implicit feedback, stop USB audio clients and reload the
USB audio module for this test session:

```sh
sudo modprobe -r snd_usb_audio
sudo modprobe snd_usb_audio implicit_fb=N ignore_ctl_error=Y skip_validation=Y
sudo uh7000ctl configure
```

This module reload affects USB audio devices globally until the module is
reloaded again or the machine reboots. It is a diagnostic gate, not yet a
persistent package policy.

The decoded Windows control-panel output/effect-mode payloads are not installed
as normal controls yet. One generated `0x42` candidate drove the local
output-to-input loopback into hard clipping and did not fully recover with
`quiet`, ALSA rebind, or usbfs reset. Treat those payloads as reverse-engineering
data only until the mixer semantics and hardware recovery path are understood.

If the analog outputs emit steady noise immediately on UH-7000 power-on or USB
attach, disconnect the output-to-input loopback before running diagnostics. The
automatic hotplug service does not send mixer writes; it only selects USB
configuration `2` and registers `snd_usb_audio`. A clean baseline must be proven
with outputs disconnected before any output loopback test is meaningful.

Before any further live output-routing experiment, the hardware must pass:

```sh
sudo uh7000ctl preflight 2
```

with zero clips on all channels while the output-to-input loopback is
disconnected. `preflight` does not play audio and does not send mixer writes.
If the front-panel meter is solid red, power-cycle the UH-7000 before testing
more controls.

Once `preflight` passes and the outputs are physically routed to the inputs, run:

```sh
sudo uh7000ctl loopback-test 3 -60
```

This command plays only after `preflight` passes. It generates a 1 kHz,
-60 dBFS, 4-channel `S24_3LE` playback stream, records the 6-channel capture
stream, reports per-channel peak/RMS/1 kHz level/clips, and fails if no return
tone is visible above -90 dBFS or if capture clips.

Research-only tooling in `tools/` can regenerate the decoded Windows helper
call-site table from a local disassembly:

```sh
python3 tools/uh7000_decode_driver_controls.py /tmp/uh7000u.dis --markdown
```

The extracted control-panel binary can also be emulated offline to regenerate
the bounded routing/effect candidate matrix:

```sh
/tmp/uh7000-emuv/bin/python tools/uh7000_cpl_emulate.py --matrix --markdown
```

The generated matrix is installed as package documentation and decodes the
eight 64-byte `0x20c` routing slices into compact route-slot strings. It is not
a live USB test plan: cases that set mixer offset `0x204` generate nonzero
request `0x42` payloads and remain research-only until `preflight` passes and
the recovery behavior is understood.

The same emulator can regenerate the decoded 0xf800 mixer/UI image offline:

```sh
/tmp/uh7000-emuv/bin/python tools/uh7000_cpl_emulate.py --f800-image --json
/tmp/uh7000-emuv/bin/python tools/uh7000_cpl_emulate.py --f800-image --output /tmp/uh7000-f800.bin
```

The default ADC/DAC 48 kHz image currently has checksum verification sum
`0x00000000` and maps to request `0x55` pages `0x007c..0x007f`. The installed
package does not upload this image automatically; the live `0x55` write path
remains gated behind an explicit environment variable, preflight, page
readback, and capture rollback checks while the semantics are being proven.

The live upload command is experimental and should only be used from a clean
baseline with physical access to power-cycle the interface:

```sh
UH7000_EXPERIMENTAL_0X55_WRITE=1 sudo -E uh7000ctl f800-upload /tmp/uh7000-f800.bin
```

If a saved backup needs to be restored manually:

```sh
UH7000_EXPERIMENTAL_0X55_WRITE=1 sudo -E uh7000ctl f800-restore /tmp/uh7000-f800-backup.xxxxxx.bin
```

For read-only live control-plane evidence, `sudo uh7000ctl state-dump /tmp`
records verified request `0x55` pages. Local hardware returns a dense
firmware/DSP-looking page at `0x1f00`; the direct Windows `f102c900` read path
for image base `0xf800` maps to pages `0x007c..0x007f`, which currently return
all `0xff`. Page `0x0002` stalls in the current Linux state, so the installed
command intentionally does not scan page indices.

## GitHub Releases

The GitHub Actions workflow builds the Debian package on pushes, pull requests,
manual runs, and `v*` tags. Tag builds publish `dist/*.deb` and `SHA256SUMS` to
the corresponding GitHub Release.

For a local diagnostic artifact:

```sh
sudo uh7000ctl report 1 > uh7000-report.json
```

The report format is documented in `docs/report-schema.json`, the safe hardware
test sequence is documented in `docs/testing.md`, and the offline CPL candidate
matrix is documented in `docs/control-plan-matrix.md`.

Release preparation is documented in `docs/release-checklist.md`. Audio and
hardware GitHub issues should use the included issue template and attach
`sudo uh7000ctl report 1` output.
