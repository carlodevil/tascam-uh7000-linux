"""Safe command-line client for UH-7000 Linux support."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

from .client import service_state
from .controller import Controller
from .device import PyUsbTransport
from .protocol import VERIFIED_STATE_PAGES, read_selector_status, read_state_page

CONFIGURE_HELPER = Path("/usr/libexec/tascam-uh7000/tascam-uh7000-configure")


def _emit(payload: Any, json_output: bool) -> None:
    if json_output or isinstance(payload, (dict, list)):
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="uh7000ctl")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="show USB, ALSA and safety state")
    sub.add_parser("topology", help="show the detected audio topology")
    sub.add_parser("state", help="show all typed service state")
    sub.add_parser("diagnostics", help="include verified read-only protocol probes")
    sub.add_parser("selector-status", help="read verified vendor selector request 0x49")

    dump = sub.add_parser("state-dump", help="dump only verified read-only request 0x55 pages")
    dump.add_argument("directory", type=Path)

    configure = sub.add_parser("configure", help="select UAC2 configuration 2 (root)")
    configure.add_argument("kernel_name", nargs="?")

    preflight = sub.add_parser("preflight", help="evaluate feedback-safe playback gates")
    preflight.add_argument("--speakers-disconnected", action="store_true")
    preflight.add_argument("--attenuated-loopback", action="store_true")
    preflight.add_argument("--baseline-peak-dbfs", type=float)

    sub.add_parser("playback-plan", help="print the per-channel guarded-ramp plan")
    playback = sub.add_parser("playback-test", help="validate gates; execution remains fail-closed")
    playback.add_argument("--speakers-disconnected", action="store_true")
    playback.add_argument("--attenuated-loopback", action="store_true")
    playback.add_argument("--baseline-peak-dbfs", type=float)
    playback.add_argument("--execute", action="store_true")
    return parser


def _state_dump(directory: Path) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=True)
    transport = PyUsbTransport()
    pages: list[dict[str, Any]] = []
    for index in VERIFIED_STATE_PAGES:
        page = read_state_page(transport, index)
        path = directory / f"uh7000-state-{index:04x}.bin"
        path.write_bytes(page.payload)
        pages.append(
            {
                "index": f"0x{index:04x}",
                "path": str(path),
                "sha256": hashlib.sha256(page.payload).hexdigest(),
                "all_ff": page.is_all_ff,
                "all_zero": page.is_all_zero,
            }
        )
    manifest = {"schema": "io.github.carlodevil.UH7000.StateDump.v1", "pages": pages}
    (directory / "uh7000-state-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    controller = Controller()
    try:
        if args.command in {"status", "state"}:
            _emit(service_state() or controller.snapshot(), args.json)
        elif args.command == "topology":
            state = service_state() or controller.snapshot()
            _emit(state["audio_topology"], args.json)
        elif args.command == "diagnostics":
            _emit(service_state("GetDiagnostics") or controller.diagnostics(), args.json)
        elif args.command == "selector-status":
            _emit({"selector_status": read_selector_status(PyUsbTransport())}, True)
        elif args.command == "state-dump":
            _emit(_state_dump(args.directory), True)
        elif args.command == "configure":
            helper = Path(os.environ.get("UH7000_CONFIGURE_HELPER", str(CONFIGURE_HELPER)))
            if not helper.exists():
                raise FileNotFoundError(f"configuration helper not found: {helper}")
            command = [str(helper)]
            if args.kernel_name:
                command.append(args.kernel_name)
            return subprocess.run(command, check=False).returncode
        elif args.command == "preflight":
            payload = controller.preflight(
                speakers_disconnected=args.speakers_disconnected,
                attenuation_confirmed=args.attenuated_loopback,
                baseline_peak_dbfs=args.baseline_peak_dbfs,
            )
            _emit(payload, True)
            return 0 if payload["safe_for_playback"] else 78
        elif args.command == "playback-plan":
            _emit(controller.playback_plan(), True)
        elif args.command == "playback-test":
            payload = controller.preflight(
                speakers_disconnected=args.speakers_disconnected,
                attenuation_confirmed=args.attenuated_loopback,
                baseline_peak_dbfs=args.baseline_peak_dbfs,
            )
            if not payload["safe_for_playback"]:
                _emit({"executed": False, "safety": payload}, True)
                return 78
            if args.execute:
                _emit(
                    {
                        "executed": False,
                        "reason": "live guarded-ramp execution awaits native Debian hardware validation",
                        "plan": controller.playback_plan(),
                    },
                    True,
                )
                return 78
            _emit({"executed": False, "dry_run": True, "plan": controller.playback_plan()}, True)
        return 0
    except (FileNotFoundError, PermissionError, RuntimeError, OSError, ValueError) as exc:
        if args.json:
            _emit({"error": str(exc)}, True)
        else:
            print(f"uh7000ctl: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
