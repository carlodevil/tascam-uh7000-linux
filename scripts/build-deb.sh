#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"
OUT_DIR="$ROOT_DIR/dist"
PACKAGE="tascam-uh7000-linux"

cd "$ROOT_DIR"
rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"
dpkg-buildpackage -us -uc -b

found=0
for artifact in "$ROOT_DIR"/../${PACKAGE}_*.deb; do
    [ -f "$artifact" ] || continue
    cp "$artifact" "$OUT_DIR/"
    found=1
done
if [ "$found" -ne 1 ]; then
    printf 'No %s Debian package was produced.\n' "$PACKAGE" >&2
    exit 1
fi
sha256sum "$OUT_DIR"/*.deb > "$OUT_DIR/SHA256SUMS"
printf '%s\n' "$OUT_DIR"
