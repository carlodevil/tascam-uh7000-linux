#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT_DIR"

sh -n src/tascam-uh7000-configure src/tascam-uh7000-pipewire src/uh7000-pipewire scripts/build-deb.sh scripts/ci-smoke.sh
bash -n completions/uh7000ctl
python3 -m compileall -q src tests tools
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m json.tool docs/report-schema.json >/dev/null
python3 -m json.tool research/windows-control-fixtures.json >/dev/null
python3 tools/validate_control_fixtures.py

if command -v pkg-config >/dev/null 2>&1 && pkg-config --exists libusb-1.0; then
    gcc -std=c11 -Wall -Wextra -Werror -O2 tools/uh7000_config1_probe.c \
        -o /tmp/uh7000-stream-smoke $(pkg-config --cflags --libs libusb-1.0) -lm
    /tmp/uh7000-stream-smoke --stdin --seconds 0
fi

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
grep -q 'GROUP="audio"' udev/90-tascam-uh7000.rules
grep -q 'MODE="0660"' udev/90-tascam-uh7000.rules
grep -q 'ACTION=="change"' udev/90-tascam-uh7000.rules
grep -q 'ATTR{authorized}=="1"' udev/90-tascam-uh7000.rules
grep -q 'CONFIGURE_ATTEMPTS="8"' src/tascam-uh7000-configure
grep -q 'did not remain selected' src/tascam-uh7000-configure
grep -q 'udevadm trigger --action=add' debian/tascam-uh7000-linux.postinst
grep -q -- '--attr-match=idVendor=0644' debian/tascam-uh7000-linux.postinst
grep -q -- '--attr-match=idProduct=8048' debian/tascam-uh7000-linux.postinst
grep -q 'module-pipe-sink' src/tascam-uh7000-pipewire
grep -q 'uh7000-stream.service' src/tascam-uh7000-pipewire

if grep -Eq 'quiet|suppress-noise|f800-upload|f800-restore|control-plan' completions/uh7000ctl; then
    echo 'research-only commands leaked into installed completion' >&2
    exit 1
fi

PYTHONPATH=src python3 -m uh7000.cli --json playback-plan >/tmp/uh7000-playback-plan.json
grep -q '"channel": 1' /tmp/uh7000-playback-plan.json
grep -q '"channel": 4' /tmp/uh7000-playback-plan.json

printf 'hardware-free smoke tests passed\n'
