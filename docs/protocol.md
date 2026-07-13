# UH-7000 Protocol Boundary

This document distinguishes production-supported USB behavior from retained
reverse-engineering evidence.

## USB audio path

The device is identified by `0644:8048`. It starts in vendor configuration 1.
Writing `2` to the matching sysfs device's `bConfigurationValue` exposes the
UAC2 topology. The hot-plug helper then registers the ID with the stock
`snd_usb_audio` driver's `new_id` interface.

The confirmed topology is 4-channel playback, 6-channel capture, `S24_3LE`,
with explicit feedback endpoint `0x85`. Configuration 2 describes the
playback USB Streaming terminal as a Digital Audio Interface (`0x0602`), not
an analog line-output terminal. This proves Linux PCM transport to the digital
endpoint but does not prove analog Master/Line output; that path depends on
proprietary mixer routing. The physical meaning of capture lanes 5 and 6
remains unverified and is labelled accordingly.

## Production vendor requests

Vendor-device IN reads supported in normal operation:

| Request | Value | Index | Length | Use |
| --- | ---: | ---: | ---: | --- |
| `0x49` | `0` | `0` | 1 | selector/control-plane status |
| `0x55` | `0` | verified page | 512 | bounded state-page inspection |

An isolated Windows capture on driver 1.02 / firmware 1.08 verified request
`0x49` values `0x00` (internal clock) and `0x02` (automatic clock). The protocol
module contains an atomic write primitive that reads the previous value,
writes the new selector, verifies readback and rolls back on mismatch. It is
exposed as the narrowly scoped `SetClockSource` D-Bus method and
`uh7000ctl clock-source` command only after explicit physical-output
disconnection confirmation. The same confirmation gates the panel control.

Linux validation on 2026-07-13, using the installed 0.2.0 beta package with
the UH-7000 in UAC2 configuration 2, confirmed `automatic -> internal ->
automatic`; each transition returned matching request-`0x49` readback and the
final selector was `0x02` (Automatic).

Verified `0x55` page indices are `0x1f00` and `0x007c..0x007f`. Page `0x0002`
is deliberately rejected because legacy hardware tests stalled it.

## Unverified writes

Requests `0x42`, `0x4d`, `0x54`, and request-`0x55` page uploads are not production
controls. They were previously exercised while an output-to-input feedback
loop was active, so clipping and apparent recovery/muting cannot establish
their semantics.

A write can be promoted only after:

1. a Windows capture starts with no physical or software loop;
2. exactly one visible control changes;
3. before-state and readback are recorded;
4. the payload is repeatable across reconnect and power cycle;
5. an isolated Linux write produces the same readback; and
6. rollback is verified without relying on output muting.

The application must fail closed if any step is missing.

The reproducible Windows evidence and SHA-256 manifest are under
`research/windows-captures/2026-07-12/`.

The archived `direct-monitor.pcap` was independently rechecked on Linux. It
contains two 64-byte request-`0x4d` writes, but neither write has a matching
vendor control read, state-page readback, or distinct endpoint-`0x83` status
notification. Endpoint `0x83` continues to report recurring meter controls
only. Direct-monitor state is therefore unknown after any reconnect and must
remain a hard playback gate; do not infer an off state from a captured `0x4d`
image or a panel default.

## Linux wiring baseline

`research/windows-control-fixtures.json` is the machine-readable handoff for
Linux implementation. It provides exact setup values, state images, changed
byte offsets and classifications. Candidate `0x4d` images must be treated as
whole-state compare-and-swap transactions: readback is not available, so the
Linux agent must first capture a known state, apply only with outputs
disconnected, restore the paired image, and confirm the visible hardware state.

Mixer Mode is a multi-request transaction (`0x54`, selector `0x49`, five
request-`0x41` writes, and a final `0x4d` image) coupled to USB reconfiguration.
Never expose its individual writes as standalone commands.

## D-Bus interface

The per-user service owns the versioned name
`io.github.carlodevil.UH7000.Control1` at object path
`/io/github/carlodevil/UH7000/Control1`. Its installed introspection document
is `io.github.carlodevil.UH7000.Control1.xml`. State payloads use the versioned
JSON schema `io.github.carlodevil.UH7000.State.v1`; hardware-changing methods
raise a safety error until their corresponding control is verified.
