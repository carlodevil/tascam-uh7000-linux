#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT_DIR"

sh -n \
    src/uh7000ctl \
    src/tascam-uh7000-configure \
    scripts/build-deb.sh \
    scripts/ci-smoke.sh \
    packaging/postinst \
    packaging/postrm
bash -n completions/uh7000ctl

python3 -m py_compile \
    tools/uh7000_probe.py \
    tools/uh7000_cpl_emulate.py \
    tools/uh7000_decode_driver_controls.py \
    tools/uh7000_iso_encoder.py

python3 - <<'PY'
from pathlib import Path
import re

text = Path("src/uh7000ctl").read_text(encoding="utf-8")
match = re.search(r"NOISE_MUTE_4D = bytes\.fromhex\(\n((?:    \".*\"\n)+)\)", text)
if not match:
    raise SystemExit("NOISE_MUTE_4D payload not found")
payload = "".join(re.findall(r'"([0-9a-f]+)"', match.group(1)))
if len(bytes.fromhex(payload)) != 64:
    raise SystemExit("NOISE_MUTE_4D must be exactly 64 bytes")
PY

python3 -m json.tool docs/report-schema.json >/tmp/uh7000-report-schema.json
grep -q 'safe_for_output_test' /tmp/uh7000-report-schema.json
grep -q 'clip_pattern' /tmp/uh7000-report-schema.json
grep -q 'all-channels' /tmp/uh7000-report-schema.json
grep -q 'playback_feedback' /tmp/uh7000-report-schema.json
grep -q 'explicit_feedback' /tmp/uh7000-report-schema.json
python3 -m json.tool docs/control-plan-matrix.json >/tmp/uh7000-control-plan-matrix.json
grep -q 'tascam-uh7000-cpl-matrix-v1' /tmp/uh7000-control-plan-matrix.json
grep -q 'adcdac/effect-0x204-1' /tmp/uh7000-control-plan-matrix.json
grep -q 'usb:v0644p8048d\*' metainfo/io.github.carlodevil.tascam_uh7000_linux.metainfo.xml
grep -q 'url type="homepage"' metainfo/io.github.carlodevil.tascam_uh7000_linux.metainfo.xml
grep -q 'control-plan' completions/uh7000ctl
grep -q 'state-dump' completions/uh7000ctl
grep -q 'f800' completions/uh7000ctl
grep -q 'f800-upload' completions/uh7000ctl
grep -q 'f800-restore' completions/uh7000ctl
grep -q 'loopback-test' completions/uh7000ctl
grep -q 'suppress-noise' completions/uh7000ctl
grep -q 'recover' completions/uh7000ctl
grep -q 'wait-clean' completions/uh7000ctl
grep -q 'input-noise' completions/uh7000ctl
grep -q '0x1F00' src/uh7000ctl
grep -q '0x007C' src/uh7000ctl
grep -q 'all_ff' src/uh7000ctl
grep -q 'tascam-uh7000-f800-image-v1' tools/uh7000_cpl_emulate.py
grep -q 'F800_RATE_TABLE' tools/uh7000_cpl_emulate.py
grep -q 'tascam-uh7000-iso-encoder-v1' tools/uh7000_iso_encoder.py
grep -q '0xf106cce0' tools/uh7000_iso_encoder.py
grep -q '0x2200fc' src/uh7000ctl
grep -q '0x220100' src/uh7000ctl
grep -q 'UH7000_EXPERIMENTAL_0X55_WRITE' src/uh7000ctl
grep -q 'f800_upload' src/uh7000ctl
grep -q 'f800_restore' src/uh7000ctl
grep -q 'uh7000ctl report' .github/ISSUE_TEMPLATE/audio-report.yml
grep -q 'lintian --tag-display-limit 0' docs/release-checklist.md
grep -q 'Sends 0x42' docs/control-plan-matrix.md
grep -q '0x20c route slots' docs/control-plan-matrix.md
grep -q '2,3,0,1,4,5,6,7' docs/control-plan-matrix.md
grep -q 'effect-0x204-1' docs/control-plan-matrix.md

./src/uh7000ctl help >/tmp/uh7000ctl-help.txt
grep -q 'control-plan' /tmp/uh7000ctl-help.txt
grep -q 'state-dump' /tmp/uh7000ctl-help.txt
grep -q 'preflight' /tmp/uh7000ctl-help.txt
grep -q 'loopback-test' /tmp/uh7000ctl-help.txt
grep -q 'report' /tmp/uh7000ctl-help.txt
grep -q 'suppress-noise' /tmp/uh7000ctl-help.txt
grep -q 'recover' /tmp/uh7000ctl-help.txt
grep -q 'wait-clean' /tmp/uh7000ctl-help.txt
grep -q 'input-noise' /tmp/uh7000ctl-help.txt
grep -q 'f800' /tmp/uh7000ctl-help.txt
grep -q 'f800-upload' /tmp/uh7000ctl-help.txt
grep -q 'f800-restore' /tmp/uh7000ctl-help.txt

./src/uh7000ctl control-plan quiet >/tmp/uh7000ctl-plan-quiet.txt
grep -q 'UH-7000 control plan: quiet' /tmp/uh7000ctl-plan-quiet.txt
grep -q 'request 0x4d' /tmp/uh7000ctl-plan-quiet.txt
grep -q 'request 0x42' /tmp/uh7000ctl-plan-quiet.txt

./src/uh7000ctl control-plan adcdac >/tmp/uh7000ctl-plan-adcdac.txt
grep -q 'UH-7000 control plan: adcdac' /tmp/uh7000ctl-plan-adcdac.txt
grep -q '2d412d412d412d41' /tmp/uh7000ctl-plan-adcdac.txt

./src/uh7000ctl control-plan noise-mute >/tmp/uh7000ctl-plan-noise-mute.txt
grep -q 'UH-7000 control plan: noise-mute' /tmp/uh7000ctl-plan-noise-mute.txt
grep -q '00002d412d412d41' /tmp/uh7000ctl-plan-noise-mute.txt
grep -q 'recovery gate' /tmp/uh7000ctl-plan-noise-mute.txt

./src/uh7000ctl control-plan routes >/tmp/uh7000ctl-plan-routes.txt
grep -q 'UH-7000 control plan: routes' /tmp/uh7000ctl-plan-routes.txt
grep -q '2,3,0,1,4,5,6,7' /tmp/uh7000ctl-plan-routes.txt
grep -q 'Effect modes add nonzero request 0x42' /tmp/uh7000ctl-plan-routes.txt

./src/uh7000ctl control-plan f800 >/tmp/uh7000ctl-plan-f800.txt
grep -q 'UH-7000 control plan: f800' /tmp/uh7000ctl-plan-f800.txt
grep -q '0x1004 bytes' /tmp/uh7000ctl-plan-f800.txt
grep -q '0x007c receives image offset 0x000..0x1ff' /tmp/uh7000ctl-plan-f800.txt
grep -q 'UH7000_EXPERIMENTAL_0X55_WRITE=1' docs/testing.md
grep -q 'does not upload the' docs/testing.md
grep -q '0xf800 image automatically' docs/testing.md

python3 tools/uh7000_iso_encoder.py --mode uh7000 --json >/tmp/uh7000-iso-encoder.json
grep -q 'tascam-uh7000-iso-encoder-v1' /tmp/uh7000-iso-encoder.json
grep -q '000001000002000005000006' /tmp/uh7000-iso-encoder.json

cat >/tmp/uh7000-decoder-fixture.dis <<'EOF'
    f1033f10:	c7 44 24 64 02 00 00 	mov    DWORD PTR [rsp+0x64],0x2
    f1033f17:	48 8d 44 24 64       	lea    rax,[rsp+0x64]
    f1033f1c:	48 89 44 24 40       	mov    QWORD PTR [rsp+0x40],rax
    f1033f29:	66 c7 44 24 30 00 09 	mov    WORD PTR [rsp+0x30],0x900
    f1033f30:	66 c7 44 24 28 01 02 	mov    WORD PTR [rsp+0x28],0x201
    f1033f37:	c6 44 24 20 01       	mov    BYTE PTR [rsp+0x20],0x1
    f1033f3c:	41 b9 01 00 00 00    	mov    r9d,0x1
    f1033f42:	41 b8 20 00 00 00    	mov    r8d,0x20
    f1033f48:	33 d2                	xor    edx,edx
    f1033f59:	e8 b2 f3 00 00       	call   0xf1043310
EOF
python3 tools/uh7000_decode_driver_controls.py /tmp/uh7000-decoder-fixture.dis >/tmp/uh7000-decoder-fixture.txt
grep -q 'req=0x01' /tmp/uh7000-decoder-fixture.txt
grep -q 'wValue=0x0201' /tmp/uh7000-decoder-fixture.txt
grep -q 'wIndex=0x0900' /tmp/uh7000-decoder-fixture.txt
grep -q 'len=2' /tmp/uh7000-decoder-fixture.txt

package_path="$(scripts/build-deb.sh | tail -n 1)"
test -f "$package_path"
dpkg-deb --info "$package_path" >/tmp/uh7000-deb-info.txt
dpkg-deb --contents "$package_path" >/tmp/uh7000-deb-contents.txt
grep -q './usr/bin/uh7000ctl' /tmp/uh7000-deb-contents.txt
grep -q './usr/share/bash-completion/completions/uh7000ctl' /tmp/uh7000-deb-contents.txt
grep -q './usr/lib/udev/rules.d/90-tascam-uh7000.rules' /tmp/uh7000-deb-contents.txt
grep -q './usr/share/metainfo/io.github.carlodevil.tascam_uh7000_linux.metainfo.xml' /tmp/uh7000-deb-contents.txt
grep -q './usr/share/man/man1/uh7000ctl.1.gz' /tmp/uh7000-deb-contents.txt
grep -q './usr/share/doc/tascam-uh7000-linux/README.md' /tmp/uh7000-deb-contents.txt
grep -q './usr/share/doc/tascam-uh7000-linux/changelog.Debian.gz' /tmp/uh7000-deb-contents.txt
grep -q './usr/share/doc/tascam-uh7000-linux/testing.md' /tmp/uh7000-deb-contents.txt
grep -q './usr/share/doc/tascam-uh7000-linux/report-schema.json' /tmp/uh7000-deb-contents.txt
grep -q './usr/share/doc/tascam-uh7000-linux/release-checklist.md' /tmp/uh7000-deb-contents.txt
grep -q './usr/share/doc/tascam-uh7000-linux/control-plan-matrix.md' /tmp/uh7000-deb-contents.txt
grep -q './usr/share/doc/tascam-uh7000-linux/control-plan-matrix.json' /tmp/uh7000-deb-contents.txt

printf 'ci-smoke passed\n'
