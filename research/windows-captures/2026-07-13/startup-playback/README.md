# UH-7000 Windows startup and analog-playback capture

This capture closes the Windows-side startup/ISO-output evidence request from
the Debian hardware session.

## Setup

- Windows 11 Home Single Language 10.0.26100, build 26100
- UH-7000 Windows driver 1.02, firmware 1.08
- USB parent: `USB\\ROOT_HUB30\\4&29fe64cb&0&0`
- Left Line Output connected directly to Analog Input 2
- Windows **Listen to this device** disabled
- speakers and headphones disconnected
- Mixer channel 2 was not changed by the automation
- source: channel 1 only, 1,250 Hz, guarded ramp from -90 to -60 dBFS
- capture opened before playback; abort thresholds were -18 dBFS, clipping,
  or growth greater than 12 dB per 100 ms

The operator explicitly authorized the direct, unattenuated connection after
validating the current configuration had no feedback loop. The run completed
without an abort and with zero clipped samples.

## USB result

The Windows product driver selected USB configuration 1. Device address 6
then carried 28,417 completed endpoint `0x02` isochronous URBs with 1,728 data
bytes each. This is the known six-packet batch of stereo S24_3LE frames.

Startup also sent the expected vendor initialization sequence:

- request `0x49` status reads;
- request `0x54` with index `0x012c`;
- request `0x4d`, 64-byte mixer image;
- request `0x42`, 256-byte DSP image; and
- the five request `0x41` 48 kHz setup writes.

The intended 1,250 Hz source was not present as 1,250 Hz in the endpoint
payload. The strongest deterministic component was 625 Hz at about
`-69.24 dBFS`, and decoded samples were repeated in adjacent pairs. This is
direct evidence that the Windows WDM four-channel source layout is transformed
by the UH-7000 configuration-1 ISO output path before its stereo USB endpoint.

## Analog return

The 25-second capture completed without clipping:

| Capture lane | Peak | RMS | 625 Hz | 1,250 Hz | Clips |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | -97.73 dBFS | -104.13 dBFS | -167.07 dBFS | -146.24 dBFS | 0 |
| 2 | -62.39 dBFS | -76.46 dBFS | -119.95 dBFS | -100.40 dBFS | 0 |
| 3 | silence | silence | silence | silence | 0 |
| 4 | silence | silence | silence | silence | 0 |

Neither the intended 1,250 Hz tone nor the transformed 625 Hz component was
returned through the same-device analog loop above the noise floor. This means
the loop capture did not validate the return path; it is not evidence that the
analog output was silent.

## Audible shared-path follow-up

The loop cable was removed and one speaker was connected to the left output.
Spotify playback was reported to work normally. A standard Windows shared
`waveOut` stereo test was then raised gradually from -40 to -20 dBFS, left
channel only, and the operator confirmed audible output.

USBPcap recorded that known-audible run in
`working-waveout-artifacts.tar.gz`. Endpoint `0x02` again contained a strongest
component near 625 Hz with repeated adjacent samples. The final one-second
USB payload block measured about -25.53 dBFS RMS. This confirms analog output
operation under the Windows shared audio path while preserving the exact
configuration-1 stream that Linux must model or bypass.

## Verified analog loopback

The speaker was removed and Left Line Output was connected to Analog Input 2
again. The known-working Windows shared `waveOut` path played a left-only
1,250 Hz ramp from -90 to -60 dBFS while the four-channel WDM-KS input was
opened first. Mixer channel 2 was not changed.

Input 2 returned the intended 1,250 Hz component at `-26.37 dBFS`; peak was
`-20.12 dBFS`, with zero clipped samples and no safety abort. Input lanes 1, 3,
and 4 remained at the noise floor or digital silence. This is the definitive
Windows analog-output mapping: left shared-audio output reaches Analog Input 2
through the physical loop.

`startup-playback-artifacts.tar.gz` contains the unmodified packet capture,
the generated 24-bit source WAV, the recorded 24-bit return WAV, and the
guarded-run JSON report.

```text
size:   24612885 bytes
sha256: 0f6322af48235e82cb63c50e9721d99a3eee8c640b545a9ed4be986f4b29c9f9
```

```text
working-waveout-artifacts.tar.gz
size:   7210572 bytes
sha256: b9ea9fe194820537441464e7c4fdae553d4fbafe8f54321703f8d66259d3b9a7
```

```text
verified-loopback-artifacts.tar.gz
size:   3504283 bytes
sha256: 8b11ab7bf41637810ad68ed7985ff66ce92283229bcd224c930af7135854a26e
```
