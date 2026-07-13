# Windows USB Capture Procedure

Use this procedure to promote UH-7000 mixer controls from reverse-engineering
evidence to production controls. A capture is valid only when one visible
Mixer Panel setting changes per capture segment and no audio playback or
physical output-to-input loop exists.

## Safety setup

1. Disconnect speakers, headphones, and every output-to-input cable.
2. Set both analog input gains to minimum and disable phantom power unless a
   microphone test specifically needs it.
3. Stop DAWs, browsers, conferencing applications, and system audio playback.
4. Record the UH-7000 firmware version and Windows driver version from the
   Mixer Panel INTERFACE page.

Do not test effects, sample-rate changes, or output routing in this capture.
Those operations can alter audio state and require a separate guarded audio
test after their USB transactions are understood.

## Capture setup

1. Install USBPcap and Wireshark on Windows.
2. Connect the UH-7000 directly to the computer, not through a hub.
3. In USBPcapCMD or the USBPcap control application, select the USB controller
   that contains `VID_0644&PID_8048`.
4. Start a full-controller capture. Do not apply a capture filter: the device
   can re-enumerate and the initial descriptor/configuration traffic is needed
   to associate later control transfers with the UH-7000.
5. Open the TASCAM UH-7000 Mixer Panel and wait ten seconds without changing
   anything. Mark this point as `baseline` in a text file beside the capture.

## Isolated control segments

For each control below, create a separate segment in the same capture or a
separate `.pcapng` file. Record the time, starting value, ending value and
whether the Mixer Panel's Apply or Save action was used.

1. Mixer mode: Multitrack to Stereo Mix, then back to Multitrack.
2. Direct monitoring: default state to the smallest single-channel change,
   then back to the default. Do not change more than one channel, pan, fader,
   solo, mute or send at once.
3. Line output source: one source change, then restore it.
4. Computer playback route: one route-slot change, then restore it.
5. Clock source: Automatic to Internal, then restore it. Skip this segment if
   an AES/EBU source is connected or clocking is unstable.

Wait at least five seconds after each Apply/Save action before the next
change. Never use a bulk preset as a substitute for an isolated control
segment.

## Startup and Analog Playback Capture

This is a separate capture from the isolated-control procedure. Its purpose is
to recover the vendor configuration-1 initialization and isochronous playback
stream that the Windows driver uses for the physical analog outputs.

### Hardware and audio setup

1. Disconnect speakers and headphones. Connect only a passive line-level cable
   from the left Line Output to Analog Input 2. Do not connect a microphone or
   an AES/EBU source.
2. Set Analog Input 2 gain to minimum, disable phantom power, and turn the
   input gain up only enough to observe a clean non-clipping return signal.
3. Close every application that may use audio. In Windows Sound settings,
   disable spatial audio, enhancements, and any communications attenuation for
   the UH-7000 playback device.
4. In the UH-7000 Mixer Panel, use its normal default route for computer
   playback to the Main/Line outputs. Do not change any Mixer Panel control
   after the device is plugged in for this capture.

### Capture sequence

1. Unplug the UH-7000 USB cable and wait ten seconds.
2. Start USBPcap on the entire USB controller that will receive the interface.
   Do not use a device filter. Save as `uh7000-startup-playback.pcapng`.
3. Plug the UH-7000 directly into that controller. Wait 20 seconds for the
   Windows driver and Mixer Panel to finish initialization.
4. Open the Mixer Panel, wait ten seconds, and do not make any control change.
5. In Audacity, select the UH-7000 as both the playback device and the recording
   device. Set the project rate to 48,000 Hz and the sample format to 24-bit.
6. Generate a stereo 1,250 Hz sine tone at -30 dBFS for five seconds. Prepend
   five seconds of digital silence and append five seconds of digital silence.
   Export this exact test signal as `uh7000-1250hz-minus30dbfs.wav`.
7. Play the 15-second file once through the UH-7000. At the same time, record
   the UH-7000 input stream in Audacity. Do not monitor the recording through
   the interface. Export it as `uh7000-left-output-to-input2.wav`.
8. Wait ten seconds after playback ends, stop USBPcap, then close Audacity and
   the Mixer Panel.

### Required operator log

Create `uh7000-startup-playback-log.txt` beside the capture with:

```text
Windows version:
UH-7000 driver version:
UH-7000 firmware version:
USB controller name:
USBPcap start time:
USB plug-in time:
Mixer Panel open time:
Tone playback start/end time:
Input recording start/end time:
Analog Input 2 gain position:
Any audible noise, clipping LED, or Windows error:
```

The important evidence is the traffic from USB plug-in through playback, not
only the packets while the tone is sounding. Do not trim, merge, filter, or
open-and-resave the packet capture before it is copied to the Linux project.

## Deliverables

Store the following together without editing the packet capture:

- `uh7000-windows-control-capture.pcapng`
- `uh7000-windows-control-log.txt` with timestamps and each exact UI action
- a Mixer Panel screenshot before and after every segment
- firmware version, driver version, Windows version and USB controller name

For the startup-and-playback procedure, also provide these unmodified files:

- `uh7000-startup-playback.pcapng`
- `uh7000-startup-playback-log.txt`
- `uh7000-1250hz-minus30dbfs.wav`
- `uh7000-left-output-to-input2.wav`

The Linux implementation will compare each segment with the baseline, identify
the bounded USB request and payload delta, replay it only with outputs
disconnected, read back the relevant state, and verify rollback after a device
reconnect. A control remains disabled unless all of those checks pass.

## Captured Baselines

The `research/windows-captures/2026-07-12/` and
`research/windows-captures/2026-07-13/` directories contain completed Windows
sessions that follow this procedure. The later session covers 37 isolated
captures on driver 1.02 and firmware 1.08, with no speakers, headphones,
loopback cabling or playback stream.

The captured `0x4d`, `0x42`, `0x54` and `0x55` transactions remain
research-only because they do not provide device readback. Request `0x49`
clock-source transitions have symmetric readback and are eligible for the
separate output-disconnected Linux validation gate.

The follow-up under
`research/windows-captures/2026-07-13/direct-monitor-readback/` additionally
records a physical reconnect. It proves that the Windows driver reasserts the
MON MIX Computer/off endpoint with request `0x54`, value `0x7f60`, index
`0x012c`; it does not obtain a hardware readback. This is a guarded force-off
candidate, not evidence that the device can report direct-monitor state.
