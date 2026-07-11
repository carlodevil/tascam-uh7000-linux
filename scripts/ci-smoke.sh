#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT_DIR"

sh -n src/tascam-uh7000-configure scripts/build-deb.sh scripts/ci-smoke.sh
bash -n completions/uh7000ctl
python3 -m compileall -q src tests tools
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m json.tool docs/report-schema.json >/dev/null

grep -q 'io.github.carlodevil.UH7000.Control1' src/uh7000/service.py
grep -q '0x85' src/uh7000/safety.py
grep -q -- '-90.0' src/uh7000/safety.py
grep -q -- '-18.0' src/uh7000/safety.py
grep -q 'direct_monitor_enabled is False' src/uh7000/safety.py
grep -q 'UNOFFICIAL LINUX PANEL' src/uh7000/qml/Main.qml
grep -q 'INTERFACE' src/uh7000/qml/Main.qml
grep -q 'MIXER' src/uh7000/qml/Main.qml
grep -q 'EFFECTS' src/uh7000/qml/Main.qml
grep -q 'usb:v0644p8048d\*' metainfo/io.github.carlodevil.tascam_uh7000_linux.metainfo.xml
grep -q 'TAG+="uaccess"' udev/90-tascam-uh7000.rules

if grep -Eq 'quiet|suppress-noise|f800-upload|f800-restore|control-plan' completions/uh7000ctl; then
    echo 'research-only commands leaked into installed completion' >&2
    exit 1
fi

PYTHONPATH=src python3 -m uh7000.cli --json playback-plan >/tmp/uh7000-playback-plan.json
grep -q '"channel": 1' /tmp/uh7000-playback-plan.json
grep -q '"channel": 4' /tmp/uh7000-playback-plan.json

printf 'hardware-free smoke tests passed\n'
