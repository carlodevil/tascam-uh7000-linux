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

The first implementation uses configuration switching plus `snd_usb_audio`
`new_id` registration. A direct class-driver bind failed on this kernel, while
registering `0644:8048` through `new_id` exposed the ALSA streams.

## Implementation Boundary

This project implements Linux integration from public USB descriptors and local
Linux behavior. It does not translate, link, redistribute, or execute the
Windows driver.
