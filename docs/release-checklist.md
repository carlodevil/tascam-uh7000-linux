# Release Checklist

Use this checklist before tagging a public package release.

## Local Verification

```sh
shellcheck completions/uh7000ctl src/uh7000ctl src/tascam-uh7000-configure scripts/build-deb.sh scripts/ci-smoke.sh packaging/postinst packaging/postrm
make test
scripts/build-deb.sh
lintian --tag-display-limit 0 dist/tascam-uh7000-linux_*_all.deb
sha256sum dist/tascam-uh7000-linux_*_all.deb > dist/SHA256SUMS
```

## Hardware-Safe Verification

These commands do not play audio or send mixer writes:

```sh
uh7000ctl status
sudo uh7000ctl control-status
sudo uh7000ctl report 1 > uh7000-report.json
sudo uh7000ctl preflight 2
```

Do not run output tests unless `preflight` passes. If capture clips or the
front-panel meter is solid red, disconnect loopback wiring and power-cycle the
UH-7000 before trying again.

## Output Verification

Only after preflight passes and the outputs are physically routed to inputs:

```sh
sudo uh7000ctl loopback-test 3 -60
```

The release is not complete if output routing is advertised as working but this
test does not detect the return tone without clipping.

## Tagging

1. Confirm `packaging/control`, `debian/changelog`, and README mention the same
   version.
2. Commit the release changes.
3. Tag with `vX.Y.Z` or another `v*` tag.
4. Push the tag and wait for GitHub Actions.
5. Confirm the GitHub Release contains the `.deb` and `SHA256SUMS`.
