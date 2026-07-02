# UH-7000 CPL Emulator Matrix

Generated with:

```sh
/tmp/uh7000-emuv/bin/python tools/uh7000_cpl_emulate.py --matrix --markdown
```

This is offline reverse-engineering evidence only. It does not send USB
controls, and it does not prove a payload is safe for live hardware. Cases that
send request `0x42` remain research-only until `sudo uh7000ctl preflight 2`
passes with no capture clipping and the recovery path is understood.

The `0x20c route slots` column decodes the eight 64-byte routing slices. A
number means the slice contains a single `0x40` hot slot; `mixed` means the
control panel produced a multi-byte pattern instead of a one-hot route.

- Schema: `tascam-uh7000-cpl-matrix-v1`
- Rate argument: `48000`
- Cases: `29`

| Case | Flags | 0x20c route slots | 0x20c nz | 0x4d nz | 0x42 nz | Sends 0x42 | Risk |
| --- | --- | --- | ---: | ---: | ---: | --- | --- |
| adc/preset | error | - | - | - | - | - | offline baseline: `emulation failed at 0x3d3706: Invalid memory fetch (UC_ERR_FETCH_UNMAPPED)` |
| adc/manual-preset | `0x7` | `mixed,mixed,0,1,4,5,6,7` | 30 | 28 | 0 | no | offline baseline |
| adcdac/preset | `0x7` | `2,3,0,1,4,5,6,7` | 8 | 28 | 0 | no | offline baseline |
| adcdac/manual-preset | `0x7` | `2,3,0,1,4,5,6,7` | 8 | 28 | 0 | no | offline baseline |
| adcdac/input-0x0 | `0x7` | `mixed,mixed,0,1,4,5,6,7` | 30 | 28 | 0 | no | offline selector candidate |
| adcdac/input-0x1 | `0x7` | `0,1,0,1,4,5,6,7` | 8 | 28 | 0 | no | offline selector candidate |
| adcdac/input-0x100 | `0x7` | `mixed,mixed,0,1,4,5,6,7` | 30 | 28 | 0 | no | offline selector candidate |
| adcdac/input-0x101 | `0x7` | `0,1,0,1,4,5,6,7` | 8 | 28 | 0 | no | offline selector candidate |
| adcdac/input-0x102 | `0x7` | `2,3,0,1,4,5,6,7` | 8 | 28 | 0 | no | offline selector candidate |
| adcdac/input-0x201 | `0x7` | `mixed,mixed,0,1,4,5,6,7` | 30 | 28 | 0 | no | offline selector candidate |
| adcdac/output-0x0 | `0x7` | `2,3,mixed,mixed,4,5,6,7` | 30 | 28 | 0 | no | offline selector candidate |
| adcdac/output-0x1 | `0x7` | `2,3,0,1,4,5,6,7` | 8 | 28 | 0 | no | offline selector candidate |
| adcdac/output-0x100 | `0x7` | `2,3,mixed,mixed,4,5,6,7` | 30 | 28 | 0 | no | offline selector candidate |
| adcdac/output-0x101 | `0x7` | `2,3,0,1,4,5,6,7` | 8 | 28 | 0 | no | offline selector candidate |
| adcdac/output-0x102 | `0x7` | `2,3,2,3,4,5,6,7` | 8 | 28 | 0 | no | offline selector candidate |
| adcdac/output-0x201 | `0x7` | `2,3,mixed,mixed,4,5,6,7` | 30 | 28 | 0 | no | offline selector candidate |
| adcdac/monitor-0 | `0x7` | `2,3,0,1,4,5,6,7` | 8 | 28 | 0 | no | offline monitor candidate |
| adcdac/monitor-1 | `0x7` | `2,3,0,1,4,5,6,7` | 8 | 28 | 0 | no | offline monitor candidate |
| adcdac/monitor-2 | `0x7` | `2,3,0,1,4,5,6,7` | 8 | 28 | 0 | no | offline monitor candidate |
| adcdac/monitor-3 | `0x7` | `2,3,0,1,4,5,6,7` | 8 | 28 | 0 | no | offline monitor candidate |
| adcdac/effect-0x204-0 | `0x7` | `2,3,0,1,4,5,6,7` | 8 | 28 | 0 | no | offline baseline |
| adcdac/effect-0x204-1 | `0xf` | `2,3,0,1,4,5,6,7` | 8 | 28 | 3 | yes | research-only: 0x204=1 caused hard loopback clipping locally |
| adcdac/effect-0x204-2 | `0xf` | `2,3,0,1,4,5,6,7` | 8 | 28 | 5 | yes | research-only: 0x204=1 caused hard loopback clipping locally |
| adcdac/effect-0x204-3 | `0xf` | `2,3,0,1,4,5,6,7` | 8 | 28 | 88 | yes | research-only: 0x204=1 caused hard loopback clipping locally |
| adcdac/effect-0x204-4 | `0xf` | `2,3,0,1,4,5,6,7` | 8 | 28 | 48 | yes | research-only: 0x204=1 caused hard loopback clipping locally |
| adcdac/effect-0x204-5 | `0xf` | `2,3,0,1,4,5,6,7` | 8 | 28 | 77 | yes | research-only: 0x204=1 caused hard loopback clipping locally |
| adcdac/effect-0x204-6 | `0xf` | `2,3,0,1,4,5,6,7` | 8 | 28 | 41 | yes | research-only: 0x204=1 caused hard loopback clipping locally |
| adcdac/effect-0x204-7 | `0xf` | `2,3,0,1,4,5,6,7` | 8 | 28 | 41 | yes | research-only: 0x204=1 caused hard loopback clipping locally |
| adcdac/effect-0x204-8 | `0xf` | `2,3,0,1,4,5,6,7` | 8 | 28 | 41 | yes | research-only: 0x204=1 caused hard loopback clipping locally |
