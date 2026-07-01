# Reverse Engineering Notes

These notes summarize the static inspection used to build the first Linux
support package.

## Official Windows Package

Downloaded package:

- `UH-7000_DR_v102_win.zip`
- SHA-256: `cb3e9425a6173f071c927770fc5daa362ee24945308769caa521aefaccbe71be`
- Official TASCAM Europe download page lists it as `Driver v1.02 for Windows`

Archive contents:

- `TASCAM_UH7000_1.02.exe`
- `E_UH-7000_RN_vD.pdf`

The installer is a Ploytec USB audio driver package. Extracted Windows payload
contains:

- `tuh7000u.sys`: USB-side Windows kernel driver
- `tuh7000a.sys`: WDM audio Windows kernel driver
- `UH7000.cpl`, `Cpl_UH7000.exe`, and helper DLLs for the control panel
- INF files for USB ID `USB\VID_0644&PID_8048` and media adapter
  `MEDIA\UH7000_AUDIOADAPTER`

No proprietary Windows binaries are included in this project.

## Linux Device Findings

Observed device:

```text
Bus 001 Device 114: ID 0644:8048 TEAC Corp. UH-7000
```

The device has two USB configurations:

- Configuration `1`: vendor-specific interfaces
- Configuration `2`: USB Audio 2.0 interfaces

Configuration `2` advertises:

- AudioControl interface, USB Audio 2.0
- 24-bit PCM streaming
- 4-channel output endpoint
- 6-channel input endpoint
- Asynchronous high-speed isochronous endpoints
- A vendor-specific interface `3` with bulk IN endpoint `0x83` and interrupt
  OUT endpoint `0x04`

The first implementation uses configuration switching plus `snd_usb_audio`
`new_id` registration. A direct class-driver bind failed on this kernel, while
registering `0644:8048` through `new_id` exposed the ALSA streams.

## Local Audio Tests

Configuration `2` capture has been verified on the local machine:

- Channel 1 microphone capture is clean.
- Channel 2 microphone capture is clean.
- The ALSA capture stream exposes 6 channels.
- The ALSA playback stream exposes 4 channels and accepts `S24_3LE` playback.

Physical output is not yet confirmed. Direct ALSA playback opens and runs, but
the device appears to require additional mixer/routing state before analog
output is audible.

Configuration `1` should not be used as a playback fallback. It exposes a
misleading vendor-specific stream when forced through `snd-usb-audio`, but
local tests timed out while setting frequency and wedged the USB device until a
power-cycle/replug.

## Control-Plane Findings

The Windows package contains UH-7000 mixer-panel strings and driver strings for
internal controls such as output volume, monitor volume, ADC boost, stereo mix
mode, and channel maps. Those controls are not exposed by the Linux
configuration `2` AudioControl descriptor. Linux currently reports only ALSA PCM
channel-map controls for this device.

Safe local probes found:

- Interface `3` bulk IN endpoint `0x83` emits 4-byte status packets of the form
  `0b b0 CONTROL VALUE`.
- Observed status controls include `0x66`, `0x67`, `0x68`, `0x69`, `0x6b`, and
  `0x6c`.
- Windows-driver request `0x49` maps to a vendor device control request. A
  device-recipient read (`bmRequestType=0xc0`, `bRequest=0x49`, `wValue=0`,
  `wIndex=0`, length `1`) succeeds while `snd-usb-audio` is bound and returned
  selector byte `0x02` locally.
- Generic vendor control scans are unsafe. A broad request scan caused the
  device to disconnect/re-enumerate during local testing.

An attempted public UAC2 Feature Unit output-volume write was rejected/timed out
because configuration `2` does not advertise that Feature Unit. That path should
not be treated as the normal Linux control plane.

## Implementation Boundary

This project implements Linux integration from public USB descriptors and local
Linux behavior. It does not translate, link, redistribute, or execute the
Windows driver.
