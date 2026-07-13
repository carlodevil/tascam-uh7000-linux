# Reverse Engineering Notes

> **Legacy evidence notice (0.2):** the original output-to-input tests were run
> while passthrough was active, forming a feedback loop. Statements below that
> attribute clipping, steady noise, or recovery to device/driver failure are not
> production conclusions. Requests `0x42`, `0x4d`, and `0x55` writes remain
> research-only until they are re-captured with all hardware and software
> monitoring paths isolated. Confirmed configuration-2 descriptors, explicit
> feedback observations, read-only requests, and offline decoders remain useful.

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

Loopback output testing with the UH-7000 outputs physically routed back to the
inputs found that ALSA playback accepts 4-channel `S24_3LE` audio, but the
played 1 kHz test tone did not appear in the 6-channel capture stream after the
currently known vendor mixer writes. Reloading `snd_usb_audio` with
`implicit_fb=N` makes ALSA use the advertised explicit feedback endpoint
`0x85`; usbmon then shows correctly sized 48 kHz output microframes on endpoint
`0x02`. The same loopback test still did not return a 1 kHz tone. This means
the remaining missing piece is not simply opening the PCM stream or sizing USB
audio packets; it is in the UH-7000 output routing/encoder state that the
Windows driver and control panel initialize.

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
- The Windows `WriteMixerData` path sends vendor device OUT request `0x4d`
  with a 64-byte payload from mixer-state offset `0x40c`, and request `0x42`
  with a 256-byte payload from mixer-state offset `0x44c`.
- Writing zeroed payloads for `0x4d` and `0x42` is locally verified to clear a
  USB-side overload/clipping state while keeping USB configuration `2` and the
  ALSA card healthy. `uh7000ctl quiet` implements exactly these two writes.
- Static inspection and local emulation of `Cpl_UH7000.exe` show the ADC/DAC
  preset sets selector-like fields to `0x102` and `0x101`. The emulated 48 kHz
  ADC/DAC preset generates a nonzero `0x40c`/request-`0x4d` block:
  `2d412d412d412d4100000000000000002d412d412d412d4100000000000000007fff7fff10401040400040000000000000000000000000000660000000000000`.
- The same driver helper sends request `0x41` for sample-rate/clock setup. A
  local 48 kHz read of `bRequest=0x41`, `wValue=0x0d00`, `wIndex=0x0101`,
  length `5` returned `81 00 2c 00 00`. Replaying the matching derived writes
  (`0x0d81`, `0x0e00`, `0x0f2c`, `0x1000`, `0x1100`, all with
  `wIndex=0x0101`) transferred successfully and left USB capture quiet, but it
  did not restore loopback-visible host playback.
- The same emulated preset changes mixer-state offset `0x20c` into eight
  64-byte one-hot routing slices. The first four slices map `(2, 3, 0, 1)`.
  Sending those slices as request `0x42`, either as one 256-byte payload or as
  individual 64-byte payloads, transferred successfully but did not restore
  loopback-visible host playback.
- Windows `WriteMixerData` flag `0x2` only copies the 0x200-byte routing block
  from incoming offset `0x20c` into driver state offset `0x354`; it is not a
  USB transfer by itself. Flag `0x4` sends `0x4d`. Flag `0x8` sends `0x42`.
  The emulated ADC/DAC preset returns flags `0x7`, so the preset does not
  request a `0x42` transfer unless a later mixer/output-effect change modifies
  offset `0x44c`.
- Selector request `0x49` values `0`, `1`, and `2`, tested with the emulated
  ADC/DAC `0x4d` block, also did not restore loopback-visible host playback.
- The bounded output-selector `0x4d` candidates from the offline CPL emulator
  were also tested in explicit-feedback mode. Tail-byte variants corresponding
  to selector groups `0/0x100/0x201`, `1`, and `0x102` transferred cleanly and
  left capture quiet, but none made the -60 dBFS 1 kHz host playback tone
  visible through the analog output-to-input loopback.
- The emulated ADC/DAC `0x4d` block did not recreate capture clipping at rest.
  It also did not make a low 1 kHz ALSA playback tone visible through the
  physical output-to-input loopback.
- `uh7000ctl control-status` implements only the verified read-only part of the
  selector path: vendor-device IN request `0x49`, `wValue=0`, `wIndex=0`,
  length `1`. It is useful for checking that the vendor control endpoint still
  responds while leaving mixer/output state untouched.
- `uh7000ctl control-plan` is a dry-run view of decoded mixer transfer plans.
  It currently prints the verified `quiet` recovery plan and the emulated
  48 kHz ADC/DAC preset plan without sending any USB request. This is the
  preferred way to compare known payloads while the live hardware is clipped or
  physically looped back.
- `uh7000ctl recover` composes the verified `quiet` blocks with before/after
  capture-health checks. It is intended to make clipped-state recovery evidence
  repeatable without playback or broader USB resets.
- A narrower Windows-derived request `0x4d` recovery block, exposed as
  `uh7000ctl suppress-noise`, clears the local constant clipped-output state
  without sending request `0x42`. The payload is the ADC/DAC 0x4d block with
  channel-0 field `+0x8` applied, which zeros byte pairs `0..1` and `16..17`.
  On the local output-to-input loopback it reduced the connected lanes from
  roughly `-4.2 dBFS RMS` with about `28%` clipped samples to about
  `-96 dBFS RMS` with zero clips after the transition settled. The subsequent
  `loopback-test 3 -60` still failed because the 1 kHz return tone stayed below
  `-90 dBFS`, so this is a recovery/mute gate rather than the final playback
  routing fix.
- `tools/uh7000_cpl_emulate.py --matrix` runs the extracted control-panel
  builder across a bounded offline candidate set and emits JSON or markdown
  evidence. The current generated matrix is installed as
  `control-plan-matrix.json` and `control-plan-matrix.md`: selector and monitor
  candidates keep Windows `WriteMixerData` at flags `0x7` with no request
  `0x42`, while offset `0x204` effect-mode candidates return flags `0xf` and
  nonzero request `0x42` payloads.
- The same matrix now decodes mixer-state offset `0x20c` as eight 64-byte
  routing slices. The normal ADC/DAC preset compact route-slot string is
  `2,3,0,1,4,5,6,7`. Input selector candidates change slices `0` and `1`;
  output selector candidates change slices `2` and `3`; monitor candidates do
  not change the decoded route slots in the current bounded set.
- Forcing mixer-state offset `0x204=1` before the same control-panel builder
  produced flags `0xf`, which would make the Windows path send both request
  `0x4d` and a nonzero request `0x42` payload. Local loopback testing showed
  this payload is unsafe: even with a -60 dBFS 1 kHz playback tone, capture
  channels clipped hard. `uh7000ctl quiet`, an ALSA interface rebind, and a
  usbfs device reset did not fully clear that overload while the physical
  output-to-input loopback remained connected. The output/effect-mode `0x204`
  payloads should therefore remain research-only until their semantics and
  recovery path are understood.
- Static driver inspection found additional Windows initialization probes and
  transfers around the mixer path. The driver checks capability-like requests
  through a helper before deciding whether to load cached 0x600 mixer state or
  generate request `0x42`. These include vendor-device reads/probes around
  request/value groups for `0x40`, `0x41`, `0x46`, `0x48`, `0x49`, and several
  class-style request `0x01` forms with nonzero `wValue`/`wIndex` pairs. They
  are decoded in the research tools and notes but are not shipped as normal
  controls yet because their side effects are not fully bounded on Linux.
- A nonzero class-style write based on decoded call site `0xf1033f59`
  (`SET_CUR`, `wValue=0x0201`, `wIndex=0x0900`, payload `c0 ff`) timed out on
  local hardware. The ALSA stream recovered after a full interface rebind, but
  this confirms that the class-style branch is not safe to brute-force.
- Static driver inspection found a request `0x55` memory-page path. The Windows
  driver reads and writes 512-byte pages with vendor request `0x55`; current
  Linux tooling only exposes the read-only side. On local hardware,
  `bmRequestType=0xc0`, `bRequest=0x55`, `wValue=0`, `wIndex=0x0002`,
  length `512` stalled with `EPIPE`, while page `0x1f00` returned 512 dense
  bytes: SHA-256
  `dd68f4c0a762cc41233fac97b812ea68f523a8d261626b488a52b3bb54430e98`,
  466 nonzero bytes, first 16 bytes
  `e06d1ff030030692bdb2e1b00003b1b0`. Direct inspection of `f102c900`
  computes a read-only page base from `0xf800 / 0x200`, so pages
  `0x007c..0x007f` were also tested. All four returned 512 bytes of `0xff`
  with SHA-256
  `9f56cda75fefeab90f6fa5d5ddc9601544b121732c5ecccab32e631060453a5d`.
  Capture stayed clean after the read-only probes. `uh7000ctl state-dump`
  therefore reads only these verified pages by default and does not issue the
  matching Windows `0x55` writes.
- The same driver path is tied to a 0x1004-byte mixer/UI image, not a small
  knob-sized register. IOCTL handlers check a descriptor-like pair
  `0x0499/0x1004`, copy a 0x1004-byte user buffer, then call either
  `f1037bf0` to upload four 512-byte pages with request `0x55` or `f102c900`
  to download four 512-byte pages with the same request. The download path's
  page indices are computed, not immediate constants. Driver strings name the
  surrounding paths `ReadMixerData uBufferLength:%d != sizeof(US3xx_UI):%d`
  and `WriteMixerData uBufferLength:%d != sizeof(US3xx_UI):%d`. This makes the
  missing output route look like part of a full vendor mixer image that Windows
  keeps in sync with device memory.
- Direct control-panel inspection found the matching 0x1004-byte wrappers in
  `Cpl_UH7000.exe`. Function `0x14002e490` uploads an image through
  `DeviceIoControl` IOCTL `0x2200fc`: it allocates a 0x1004-byte buffer, stores
  the caller-provided base dword, copies 0x800 bytes of image data to buffer
  offset `0x4`, and expects the driver to return a 0x1004-byte verification
  buffer whose second 0x800-byte half matches the original image. Function
  `0x14002e5f0` downloads the same image through IOCTL `0x220100`, then copies
  the returned buffer offset `0x804` back to the caller. The caller at
  `0x1400108b0` uses base `0xf800`, matching request `0x55` pages
  `0x007c..0x007f`.
- The decoded `0xf800` image layout is now modeled offline by
  `tools/uh7000_cpl_emulate.py --f800-image`. The image is 0x800 bytes:
  six 0x100-byte rate-specific blocks copied from mixer-state offset `0x44c`
  for 44100, 48000, 88200, 96000, 176400, and 192000 Hz; a current 0x40-byte
  request-`0x4d` block copied from mixer-state offset `0x40c` into image offset
  `0x600`; footer fields near `0x7f0`; and a final additive big-endian dword
  checksum at `0x7fc`. The default ADC/DAC 48 kHz emulation currently verifies
  to checksum sum `0x00000000` and produces full-image SHA-256
  `c027d6c998809a52b5726f7392706e0dc6881bfcbe49fa0bc8fba9765123483f`.
  This remains offline evidence only; the installed package does not issue the
  corresponding request `0x55` writes automatically. Experimental live uploads
  are gated behind `UH7000_EXPERIMENTAL_0X55_WRITE=1`, preflight, page readback,
  backup, and immediate capture rollback checks.
- Driver strings and xrefs show Windows-only paths named `LOAD MIXER BINARIES
  UH7000`, `ISO OUT ENCODER PROD_TEAC_UH7000`, `modified premixer`, `modified
  mixer data`, and `PGDevice::setSelectors`. The `WriteMixerData` path sends
  USB request `0x4d` and sometimes `0x42`, but flag `0x2` only copies a routing
  block into Windows driver memory. The ISO OUT encoder path also installs a
  product-specific encoder function pointer. This is the main reason the Linux
  implementation is harder than replaying the visible control-panel requests:
  part of the Windows behavior appears to be host-driver state used while
  preparing isochronous output, not a standalone USB control transfer.
- The decoded ISO OUT encoder path now has a local model in
  `tools/uh7000_iso_encoder.py`. The UH-7000 product branch logs
  `ISO OUT ENCODER PROD_TEAC_UH7000` at `0xf1021641` and installs either the
  generic encoder `0xf106c850` or the UH-7000-specific encoder `0xf106cce0`
  depending on a descriptor/status bit. The generic encoder packs each 32-bit
  left-aligned source sample into 3 little-endian bytes. The UH-7000 encoder
  consumes a virtual 8-slot source layout and emits a 4-channel endpoint frame
  from source slots `0,1,4,5`, skipping slots `2,3` and `6,7`. A second generic
  branch at `0xf1021724` can install `0xf106c930`, which packs stereo pairs in
  swapped order. Because the loopback test plays the same 1 kHz tone on all
  four ALSA channels, channel order alone should not erase the tone; the more
  important finding is that Windows does product-specific output preparation in
  the USB driver while Linux currently relies on the standard class-driver
  path for configuration `2`.
- A full-controller Windows startup/playback capture now confirms the product
  driver selects configuration `1`, sends the `0x49`/`0x54`/`0x4d`/`0x42` and
  five-write `0x41` initialization sequence, then submits stereo S24_3LE data
  on endpoint `0x02` in 1,728-byte URBs. A channel-1-only 1,250 Hz guarded
  source appeared in the endpoint payload as adjacent repeated samples with a
  strongest component at 625 Hz, about -69.24 dBFS. Neither 625 Hz nor 1,250 Hz
  was visible above the Analog Input 2 return noise floor. A follow-up using
  the standard Windows shared `waveOut` stereo path at -20 dBFS was audible
  through a left speaker. Its captured endpoint stream again showed repeated
  adjacent samples and a strongest component near 625 Hz. Analog output is
  therefore confirmed under Windows; the failed same-device return was not
  evidence of a silent output. Raw evidence and decoded metrics are under
  `research/windows-captures/2026-07-13/startup-playback/`.

The helper call-site table can be regenerated from an objdump-style driver
disassembly:

```sh
python3 tools/uh7000_decode_driver_controls.py /tmp/uh7000u.dis --markdown
```

High-signal decoded call sites from the current `tuh7000u.sys` disassembly:

| Call site | Request | wValue | wIndex | Length | edx | r8 | r9 | Notes |
| --- | --- | --- | --- | ---: | --- | --- | --- | --- |
| `0xf1033f59` | `0x01` | `0x0201` | `0x0900` | 2 | `0x0` | `0x20` | `0x1` | USB class/interface-style request |
| `0xf1033fbc` | `0x01` | `0x0202` | `0x0900` | 2 | `0x0` | `0x20` | `0x1` | USB class/interface-style request |
| `0xf103401f` | `0x01` | `0x0100` | `0x0900` | 1 | `0x0` | `0x20` | `0x1` | USB class/interface-style request |
| `0xf1034082` | `0x01` | `0x0200` | `0x0a00` | 2 | `0x0` | `0x20` | `0x1` | USB class/interface-style request |
| `0xf10340e5` | `0x01` | `0x0100` | `0x0a00` | 1 | `0x0` | `0x20` | `0x1` | USB class/interface-style request |
| `0xf103414b` | `0x01` | `0x0700` | `0x0a00` | 1 | `0x0` | `0x20` | `0x1` | USB class/interface-style request |
| `0xf10341ae` | `0x01` | `0x0200` | `0x0d00` | 2 | `0x0` | `0x20` | `0x1` | USB class/interface-style request |
| `0xf1034211` | `0x01` | `0x0100` | `0x0d00` | 1 | `0x0` | `0x20` | `0x1` | USB class/interface-style request |
| `0xf1034288` | `0x01` | `0x02ff` | `0x0200` | 5 | `0x0` | `0x20` | `0x1` | USB class/interface-style request |
| `0xf1034308` | `0x01` | `0x0a00` | `0x0900` | 5 | `0x0` | `0x20` | `0x1` | USB class/interface-style request |
| `0xf1036a58` | `0x4d` | `0x0000` | `0x0000` | 64 | `0x0` | `0x40` | `?` | UH-7000 vendor control family |
| `0xf1036b11` | `0x42` | `0x0000` | `0x0000` | 256 | `0x0` | `0x40` | `?` | UH-7000 vendor control family |
| `0xf1037337` | `0x49` | `0x0000` | `0x0001` | 1 | `0x80` | `0x40` | `?` | UH-7000 vendor control family |
| `0xf10375d0` | `0x41` | `0x0d00` | `0x0101` | 2 | `0x80` | `0x40` | `?` | UH-7000 vendor control family |

The `Length`, `edx`, `r8`, and `r9` columns are raw helper-call arguments from
the Windows driver, not a direct libusb `bmRequestType` contract. Linux control
transfers are only promoted from this table after a bounded local test confirms
the actual USB request type, payload length, and recovery behavior.
The decoder deliberately omits helper calls whose request fields are computed
through registers immediately before the call. Request `0x55` page transfers
fall into that category and are documented from direct disassembly inspection
plus live read-only probes instead of from the immediate call-site table.

Live output-routing tests are currently gated on hardware recovery. The next
test must start with the analog output-to-input loopback disconnected and
`sudo uh7000ctl preflight 2` passing. That command checks configuration `2`,
`snd_usb_audio` binding, 4-channel playback, 6-channel capture, vendor request
`0x49`, and zero full-scale capture clips. A solid red front-panel meter is
treated as an overload/latched state, not a valid baseline for additional mixer
writes.

After preflight passes, `sudo uh7000ctl loopback-test 3 -60` is the repeatable
output verification command. It calls `preflight` before playback, generates a
low 1 kHz test tone on all four host playback channels, records the six capture
channels, and reports peak/RMS/1 kHz/clipping per channel. It fails if no return
tone exceeds -90 dBFS or if any captured sample clips.

`sudo uh7000ctl report 1` emits a JSON diagnostic report with USB configuration,
driver bindings, ALSA stream text, parsed playback feedback mode, vendor
selector status, capture health, and a `safe_for_output_test` boolean. Output
tests require explicit feedback endpoint `0x85` and `Implicit Feedback Mode:
No`; implicit-feedback reports are kept out of the safe output-test gate. This
report is intended for release evidence and for comparing hardware state before
and after control-plane changes.

An attempted public UAC2 Feature Unit output-volume write was rejected/timed out
because configuration `2` does not advertise that Feature Unit. That path should
not be treated as the normal Linux control plane.

## Implementation Boundary

This project implements Linux integration from public USB descriptors and local
Linux behavior. It does not translate, link, redistribute, or execute the
Windows driver.
