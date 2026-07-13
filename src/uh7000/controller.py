"""Shared controller used by D-Bus, CLI and the panel."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import __version__
from .audio import inspect_audio, pipewire_loopbacks
from .device import PyUsbTransport, device_status
from .models import ClockSource as MixerClockSource
from .models import EffectsState, MixerState
from .protocol import ClockSource as ProtocolClockSource
from .protocol import (
    ControlTransport,
    parse_firmware_hint,
    read_selector_status,
    read_state_page,
    set_clock_source as write_clock_source,
)
from .safety import evaluate_preflight, playback_channel_plan


class UnverifiedControlError(PermissionError):
    pass


@dataclass
class Controller:
    mixer: MixerState = field(default_factory=MixerState)
    effects: EffectsState = field(default_factory=EffectsState)
    transport_factory: Callable[[], ControlTransport] = PyUsbTransport

    def snapshot(self) -> dict[str, Any]:
        device = device_status()
        topology = inspect_audio()
        loops = pipewire_loopbacks()
        safety = evaluate_preflight(device, topology, self.mixer, loops)
        return {
            "schema": "io.github.carlodevil.UH7000.State.v1",
            "version": __version__,
            "device": device.to_dict(),
            "audio_topology": topology.to_dict(),
            "mixer": self.mixer.to_dict(),
            "effects": self.effects.to_dict(),
            "safety": safety.to_dict(),
        }

    def diagnostics(self) -> dict[str, Any]:
        result = self.snapshot()
        result["protocol"] = {
            "selector_status": None,
            "firmware_hint": None,
            "vendor_status_packets": [],
            "error": None,
        }
        try:
            transport = PyUsbTransport()
            result["protocol"]["selector_status"] = read_selector_status(transport)
            page = read_state_page(transport, 0x1F00)
            result["protocol"]["firmware_hint"] = parse_firmware_hint(page)
            result["protocol"]["vendor_status_packets"] = [
                packet.to_dict() for packet in transport.read_vendor_status()
            ]
        except Exception as exc:  # diagnostics must remain available when USB access is absent
            result["protocol"]["error"] = str(exc)
        return result

    def preflight(
        self,
        *,
        speakers_disconnected: bool,
        attenuation_confirmed: bool,
        baseline_peak_dbfs: float | None,
    ) -> dict[str, Any]:
        state = evaluate_preflight(
            device_status(),
            inspect_audio(),
            self.mixer,
            pipewire_loopbacks(),
            speakers_disconnected=speakers_disconnected,
            attenuation_confirmed=attenuation_confirmed,
            baseline_peak_dbfs=baseline_peak_dbfs,
        )
        return state.to_dict()

    def apply_mixer_patch(self, patch: dict[str, Any]) -> MixerState:
        unverified = sorted(set(patch) - set(self.mixer.verified_controls))
        if unverified:
            raise UnverifiedControlError(
                "refusing unverified hardware controls: " + ", ".join(unverified)
            )
        for key, value in patch.items():
            setattr(self.mixer, key, value)
        self.mixer.validate()
        return self.mixer

    def set_clock_source(self, source: str, *, outputs_disconnected: bool) -> MixerState:
        """Set the one hardware control with verified Linux write/readback.

        Changing a clock source can interrupt audio, so this remains behind an
        explicit physical-output confirmation even though its USB transaction is
        verified and rollback-safe.
        """
        if not outputs_disconnected:
            raise UnverifiedControlError(
                "physical output disconnection must be confirmed before changing clock source"
            )
        sources = {
            "automatic": ProtocolClockSource.AUTOMATIC,
            "internal": ProtocolClockSource.INTERNAL,
        }
        try:
            target = sources[source]
        except KeyError as exc:
            raise ValueError("clock source must be 'automatic' or 'internal'") from exc

        observed = write_clock_source(self.transport_factory(), target)
        self.mixer.clock_source = (
            MixerClockSource.AUTOMATIC
            if observed is ProtocolClockSource.AUTOMATIC
            else MixerClockSource.INTERNAL
        )
        return self.mixer

    def reset(self) -> None:
        raise UnverifiedControlError("hardware reset is locked until write/readback is verified")

    def apply_preset(self, name: str) -> None:
        if name not in {"adc", "adcdac"}:
            raise ValueError("preset must be 'adc' or 'adcdac'")
        raise UnverifiedControlError(
            f"{name} preset is locked until hardware write/readback is verified"
        )

    @staticmethod
    def playback_plan() -> list[dict[str, object]]:
        return playback_channel_plan()

    @staticmethod
    def write_json(path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
