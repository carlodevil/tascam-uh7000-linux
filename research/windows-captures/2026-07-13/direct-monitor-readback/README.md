# Direct-monitor startup and reconnect evidence

This follow-up isolates the global **MON MIX** slider after Linux testing found
that the earlier `direct-monitor.pcap` contained no readable device state.

## Safety and starting state

- Driver 1.02, firmware 1.08, USB 2.0, 24-bit/48 kHz, Multitrack mode.
- The physical output-to-input loop was disconnected.
- No playback stream was opened.
- Analog 1 and Analog 2 were muted with their faders at minimum.
- MON MIX started fully at **Computer**, which is the panel's direct-monitor-off
  endpoint.
- Line output remained `Computer 1 and 2`; no channel-2 level was changed.

## Panel restart and isolated transition

`panel-restart-and-transition.pcap` records this sequence:

1. Five seconds of idle traffic with MON MIX at Computer.
2. Close and reopen the Mixer Panel. It reopened showing Computer.
3. Move MON MIX partway toward Input.
4. Restore MON MIX fully to Computer.
5. Close and reopen the panel again. It again showed Computer.

Closing or opening the panel produced no monitor-state USB read or write. The
only monitor transactions are the two deliberate changes:

| Time | Request | Value | Index | Meaning |
| ---: | ---: | ---: | ---: | --- |
| 32.080509 s | `0x54` OUT | `0x586c` | `0x012c` | partway toward Input |
| 44.103292 s | `0x54` OUT | `0x7f60` | `0x012c` | fully Computer / monitoring off |

This proves that reopening the panel displays driver-cached state; it does not
read MON MIX from the device.

## Physical USB reconnect

`usb-reconnect-live.pcap` records a physical disconnect and reconnect. The
device reappears at 7.975 seconds as USB address 6. Before any panel action,
the Windows driver sends:

```text
40 54 60 7f 2c 01 00 00
```

Decoded: vendor-device OUT request `0x54`, value `0x7f60`, index `0x012c`,
zero-length data stage. This is exactly the isolated Computer/off value above.
The driver then writes its request-`0x4d` mixer image and request-`0x42` DSP
image as part of startup. The panel visibly remained fully at Computer after
reconnect.

There is still no `0x54` readback and no distinct endpoint-`0x83` notification
for this state. Endpoint `0x83` continues to carry recurring meter values.

## Implementation consequence

The new evidence does **not** create positive readback. It does prove the
Windows driver's reconnect policy: it actively reasserts `0x7f60/0x012c`
rather than discovering the state from hardware.

A Linux implementation may use that transaction only as a guarded
`force-direct-monitor-off` primitive:

- outputs physically disconnected;
- no active analog stream;
- send the exact request after every reconnect;
- fail playback closed if the write fails;
- record the state as `forced_off_unverified`, never `readback_off`; and
- retain the existing playback gate until independent physical verification
  establishes an acceptable safety policy without protocol readback.

## Raw evidence hashes

```text
61ade344cdd1737c90e53a1c2579670c4c277294afb5dec5834f9ecaa3eb4507  panel-restart-and-transition.pcap
c1456d792615078b6681e4a1bb8aa09d3055d5cac6eff51c44b88d37b18ac8d3  usb-reconnect-live.pcap
```

