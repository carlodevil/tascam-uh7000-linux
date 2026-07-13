# UH-7000 Linux Support

Unofficial, clean-room Debian integration and control panel for the TASCAM
UH-7000 USB audio interface.

The UH-7000 starts in a vendor-specific USB configuration. Configuration 2 is
a USB Audio 2.0 topology that the stock Linux `snd_usb_audio` driver can use.
This project selects configuration 2 on hot-plug, registers `0644:8048`, and
provides a feedback-safe control service, CLI, and Qt Quick panel.

## Status: 0.2 beta

Confirmed from the legacy implementation and local hardware:

- USB ID `0644:8048`
- configuration 2 exposes UAC2 audio
- 4-channel `S24_3LE` playback
- 6-channel `S24_3LE` capture
- explicit playback feedback endpoint `0x85`
- stock `snd_usb_audio` works after `new_id` registration
- verified read-only vendor requests `0x49` and bounded `0x55` pages
- verified transactional `0x49` clock-source control: Automatic and Internal,
  with readback and rollback validation while physical outputs are disconnected

Only clock source is enabled for hardware writes, and it requires explicit
physical-output disconnection confirmation. Mixer, routing, direct-monitor,
and effects writes remain locked until each control is captured in isolation
and verified by readback. Earlier clipped-loopback observations are not treated
as device failures: the same-device test formed a feedback loop while
passthrough was active.

The configuration-2 playback terminal is advertised as a USB Digital Audio
Interface. Linux can stream four PCM channels to that endpoint, but it is not
the verified analog path. Analog Master/Line playback is provided explicitly
by the packaged configuration-1 backend described below.

## Analog playback

`uh7000-stream` is the verified configuration-1 analog playback backend. It
accepts stereo 48 kHz `S24_3LE` raw PCM, temporarily claims the vendor stream,
then restores configuration 2 and the normal ALSA capture/control card when it
exits. It uses no mixer or DSP write.

```sh
ffmpeg -i music.wav -f s24le -ac 2 -ar 48000 - | \
  uh7000-stream --stdin --seconds 0 --execute
```

For a bounded diagnostic tone, first disconnect speakers and headphones:

```sh
uh7000-stream --seconds 2 --execute
```

The local analog loopback validation returned a generated 1250 Hz stream on
Analog Input 2 at -1.75 dBFS. It is therefore a real analog-output path, not
an ALSA routing plan. On PipeWire-Pulse desktops, the packaged per-user bridge
provides an opt-in virtual sink:

```sh
uh7000-pipewire enable
uh7000-pipewire set-default
# Later: uh7000-pipewire disable
```

The bridge creates `uh7000-analog`, a stereo 48 kHz sink backed by the same
configuration-1 stream. Disable it before using UAC2 playback or changing
controls that require the normal configuration-2 card.

## Safety model

`uh7000ctl preflight` refuses playback unless all of these are true:

- USB configuration 2 is selected;
- the stock ALSA driver exposes 4 playback and 6 capture channels;
- explicit feedback endpoint `0x85` is confirmed;
- no PipeWire/ALSA loopback is detected;
- DSP direct monitoring is positively read back as off;
- speakers/headphones are confirmed disconnected;
- an attenuated line-level loop is confirmed; and
- a measured capture baseline is below the abort threshold.

The planned hardware test uses different tones on each playback channel and a
guarded ramp from -90 to -60 dBFS. It aborts at -18 dBFS or when capture grows
by more than 12 dB in one 100 ms guard window.

## Components

- `uh7000d`: per-user D-Bus service at
  `io.github.carlodevil.UH7000.Control1`
- `uh7000-panel`: clean-room Interface, Mixer, and Effects panel
- `uh7000ctl`: state, topology, diagnostics, safe preflight, and read-only USB
  inspection
- `tascam-uh7000-configure`: root-only UAC2 hot-plug helper
- `uh7000-stream`: explicit configuration-1 analog playback backend
- `uh7000-pipewire`: opt-in PipeWire-Pulse analog sink manager
- UCM2 and WirePlumber profiles with stable UH-7000 naming

## Build on Debian 13

```sh
sudo apt build-dep ./
dpkg-buildpackage -us -uc -b
```

For a source-tree development environment:

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[test,gui]'
pytest
```

## Install and inspect

```sh
sudo apt install ../tascam-uh7000-linux_0.2.0~beta9_amd64.deb
uh7000ctl --json status
uh7000ctl --json topology
uh7000ctl --json diagnostics
uh7000-panel
```

With every physical output disconnected, the verified clock-source control can
be changed transactionally:

```sh
uh7000ctl --json clock-source internal --outputs-disconnected --execute
uh7000ctl --json clock-source automatic --outputs-disconnected --execute
```

If the device was already connected:

```sh
sudo uh7000ctl configure
```

Playback remains locked while DSP direct-monitor readback is unverified:

```sh
uh7000ctl --json preflight \
  --speakers-disconnected \
  --attenuated-loopback \
  --baseline-peak-dbfs -80
```

## Research boundary

Legacy Windows-driver decoders, mixer image builders, and experimental payload
matrices remain in `tools/` and `docs/` as research evidence. They are not
installed. The production protocol module exposes only verified read-only
requests. No TASCAM/Ploytec binaries, firmware, logos, or interface artwork are
included.

See [protocol documentation](docs/protocol.md), [safe hardware tests](docs/testing.md),
and [legacy reverse-engineering notes](docs/reverse-engineering-notes.md).

## License

MIT. TASCAM and UH-7000 are trademarks of their respective owner. This project
is unofficial and is not endorsed by TASCAM or TEAC.
