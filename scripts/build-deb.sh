#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"
CONTROL="$ROOT_DIR/packaging/control"
PACKAGE="$(awk '/^Package:/{print $2}' "$CONTROL")"
VERSION="$(awk '/^Version:/{print $2}' "$CONTROL")"
ARCH="$(awk '/^Architecture:/{print $2}' "$CONTROL")"
BUILD_DIR="$ROOT_DIR/build"
PKG_DIR="$BUILD_DIR/${PACKAGE}_${VERSION}_${ARCH}"
OUT_DIR="$ROOT_DIR/dist"

rm -rf "$PKG_DIR"
mkdir -p \
    "$PKG_DIR/DEBIAN" \
    "$PKG_DIR/usr/bin" \
    "$PKG_DIR/usr/libexec/tascam-uh7000" \
    "$PKG_DIR/usr/lib/systemd/system" \
    "$PKG_DIR/usr/lib/udev/rules.d" \
    "$PKG_DIR/usr/share/bash-completion/completions" \
    "$PKG_DIR/usr/share/metainfo" \
    "$PKG_DIR/usr/share/man/man1" \
    "$PKG_DIR/usr/share/doc/$PACKAGE"

cp "$CONTROL" "$PKG_DIR/DEBIAN/control"
cp "$ROOT_DIR/packaging/postinst" "$PKG_DIR/DEBIAN/postinst"
cp "$ROOT_DIR/packaging/postrm" "$PKG_DIR/DEBIAN/postrm"
if [ -s "$ROOT_DIR/packaging/prerm" ]; then
    cp "$ROOT_DIR/packaging/prerm" "$PKG_DIR/DEBIAN/prerm"
fi
chmod 0755 "$PKG_DIR/DEBIAN/postinst" "$PKG_DIR/DEBIAN/postrm"
if [ -f "$PKG_DIR/DEBIAN/prerm" ]; then
    chmod 0755 "$PKG_DIR/DEBIAN/prerm"
fi

cp "$ROOT_DIR/src/uh7000ctl" "$PKG_DIR/usr/bin/uh7000ctl"
cp "$ROOT_DIR/src/tascam-uh7000-configure" "$PKG_DIR/usr/libexec/tascam-uh7000/tascam-uh7000-configure"
chmod 0755 "$PKG_DIR/usr/bin/uh7000ctl" "$PKG_DIR/usr/libexec/tascam-uh7000/tascam-uh7000-configure"

cp "$ROOT_DIR/systemd/tascam-uh7000-configure@.service" "$PKG_DIR/usr/lib/systemd/system/tascam-uh7000-configure@.service"
cp "$ROOT_DIR/udev/90-tascam-uh7000.rules" "$PKG_DIR/usr/lib/udev/rules.d/90-tascam-uh7000.rules"
cp "$ROOT_DIR/completions/uh7000ctl" "$PKG_DIR/usr/share/bash-completion/completions/uh7000ctl"
cp "$ROOT_DIR/metainfo/io.github.carlodevil.tascam_uh7000_linux.metainfo.xml" "$PKG_DIR/usr/share/metainfo/io.github.carlodevil.tascam_uh7000_linux.metainfo.xml"

cp "$ROOT_DIR/README.md" "$PKG_DIR/usr/share/doc/$PACKAGE/README.md"
cp "$ROOT_DIR/LICENSE" "$PKG_DIR/usr/share/doc/$PACKAGE/copyright"
gzip -9cn "$ROOT_DIR/debian/changelog" > "$PKG_DIR/usr/share/doc/$PACKAGE/changelog.Debian.gz"
if [ -f "$ROOT_DIR/docs/reverse-engineering-notes.md" ]; then
    cp "$ROOT_DIR/docs/reverse-engineering-notes.md" "$PKG_DIR/usr/share/doc/$PACKAGE/reverse-engineering-notes.md"
fi
if [ -f "$ROOT_DIR/docs/testing.md" ]; then
    cp "$ROOT_DIR/docs/testing.md" "$PKG_DIR/usr/share/doc/$PACKAGE/testing.md"
fi
if [ -f "$ROOT_DIR/docs/report-schema.json" ]; then
    cp "$ROOT_DIR/docs/report-schema.json" "$PKG_DIR/usr/share/doc/$PACKAGE/report-schema.json"
fi
if [ -f "$ROOT_DIR/docs/release-checklist.md" ]; then
    cp "$ROOT_DIR/docs/release-checklist.md" "$PKG_DIR/usr/share/doc/$PACKAGE/release-checklist.md"
fi
if [ -f "$ROOT_DIR/docs/control-plan-matrix.md" ]; then
    cp "$ROOT_DIR/docs/control-plan-matrix.md" "$PKG_DIR/usr/share/doc/$PACKAGE/control-plan-matrix.md"
fi
if [ -f "$ROOT_DIR/docs/control-plan-matrix.json" ]; then
    cp "$ROOT_DIR/docs/control-plan-matrix.json" "$PKG_DIR/usr/share/doc/$PACKAGE/control-plan-matrix.json"
fi
gzip -9cn "$ROOT_DIR/docs/uh7000ctl.1" > "$PKG_DIR/usr/share/man/man1/uh7000ctl.1.gz"

find "$PKG_DIR" -type d -exec chmod 0755 {} +
find "$PKG_DIR" -type f -exec chmod 0644 {} +
chmod 0755 "$PKG_DIR/DEBIAN/postinst" "$PKG_DIR/DEBIAN/postrm"
if [ -f "$PKG_DIR/DEBIAN/prerm" ]; then
    chmod 0755 "$PKG_DIR/DEBIAN/prerm"
fi
chmod 0755 "$PKG_DIR/usr/bin/uh7000ctl" "$PKG_DIR/usr/libexec/tascam-uh7000/tascam-uh7000-configure"
chmod 0644 "$PKG_DIR/usr/share/man/man1/uh7000ctl.1.gz"
chmod 0644 "$PKG_DIR/usr/share/doc/$PACKAGE/changelog.Debian.gz"

mkdir -p "$OUT_DIR"
dpkg-deb --build --root-owner-group "$PKG_DIR" "$OUT_DIR/${PACKAGE}_${VERSION}_${ARCH}.deb"
printf '%s\n' "$OUT_DIR/${PACKAGE}_${VERSION}_${ARCH}.deb"
