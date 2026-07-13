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

## Deliverables

Store the following together without editing the packet capture:

- `uh7000-windows-control-capture.pcapng`
- `uh7000-windows-control-log.txt` with timestamps and each exact UI action
- a Mixer Panel screenshot before and after every segment
- firmware version, driver version, Windows version and USB controller name

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
