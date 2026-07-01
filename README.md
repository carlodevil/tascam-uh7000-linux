# TASCAM UH-7000 Linux Support

Debian package for the TASCAM UH-7000 USB audio interface.

The UH-7000 powers up in a vendor-specific USB configuration. The same device
also exposes a USB Audio 2.0 configuration. This package switches the device to
that USB Audio 2.0 configuration on hotplug and registers the device ID with
the standard `snd_usb_audio` driver.

## Status

Early hardware support package.

Known local findings:

- USB ID: `0644:8048`
- Manufacturer/product strings: `TASCAM` / `UH-7000`
- Default Linux-visible configuration: `1`, vendor-specific
- USB Audio 2.0 configuration: `2`
- Configuration `2` advertises 24-bit PCM, 4 output channels, and 6 input channels

This project does not include TASCAM/Ploytec Windows driver binaries.

## Build

```sh
scripts/build-deb.sh
```

The package is written to `dist/`.

## Install

```sh
sudo dpkg -i dist/tascam-uh7000-linux_0.1.1-1_all.deb
```

Unplug and replug the UH-7000, then check:

```sh
uh7000ctl status
aplay -l
arecord -l
```

If the device is already plugged in, you can manually trigger configuration:

```sh
sudo uh7000ctl configure
```

## Uninstall

```sh
sudo dpkg -r tascam-uh7000-linux
```

## How It Works

The package installs:

- A udev rule for USB ID `0644:8048`
- A systemd oneshot service for hotplug handling
- A root-only helper that writes `2` to the device's `bConfigurationValue`
- A `snd_usb_audio` `new_id` registration for `0644:8048`
- `uh7000ctl`, a diagnostic CLI

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
