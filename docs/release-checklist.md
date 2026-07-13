# Release Checklist

## Hardware-free

- [x] `python3 -m compileall -q src tests tools`
- [x] `PYTHONPATH=src python3 -m unittest discover -s tests -v`
- [x] Debian 13 `dpkg-buildpackage -us -uc -b`
- [x] `lintian --tag-display-limit 0 ../tascam-uh7000-linux_*.deb`
- [x] package install, upgrade from 0.1.34, and purge/reinstall tests
- [x] package reinstall and user-service restart on Debian 13
- [x] offscreen Qt Interface/Mixer/Effects rendering test
- [x] no research-only `0x42`, `0x4d`, or `0x55` write command in the package
- [x] isolated Windows captures recorded for clock, mode, monitor and routing controls
- [x] request `0x49` clock values have symmetric Windows readback and rollback evidence

## Native device

- [ ] configuration 2 and `snd_usb_audio` bind after 20 reconnects
- [x] 4 playback / 6 capture channels and explicit endpoint `0x85` on one Debian 13 host
- [ ] physical mapping characterized with isolated sources
- [ ] PipeWire graph contains no unintended capture-to-playback path
- [ ] direct-monitor state positively read back as off before playback
- [ ] guarded channel test passes with physical attenuation
- [ ] 30-minute duplex run at every advertised sample rate
- [ ] eight-hour duplex runs at 48, 96 and 192 kHz
- [ ] suspend/resume, invalid digital clock and unplug recovery pass
- [ ] every enabled mixer/effect control has capture, readback and rollback evidence
- [x] request `0x49` atomic clock change passes an output-disconnected Linux test

## Publication

- [ ] current legacy main tip tagged `legacy-0.1.34`
- [ ] draft PR documents the feedback-loop root cause and safety change
- [x] GitHub Actions succeeds on Debian 13
- [ ] `v0.2.0-beta.1` release contains `.deb` and `SHA256SUMS`
- [ ] stable release deferred until two additional UH-7000 systems validate duplex audio
# Windows-derived control evidence

Before enabling any mixer, routing, clock or effect write, retain an isolated
Windows capture following `docs/windows-usb-capture.md`. The control must have
repeatable before/after payloads, Linux readback and rollback evidence.
