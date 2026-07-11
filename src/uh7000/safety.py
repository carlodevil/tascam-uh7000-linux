"""Fail-closed feedback prevention and guarded-ramp policy."""

from __future__ import annotations

from dataclasses import dataclass

from .models import AudioTopology, DeviceStatus, MixerState, SafetyState

ABORT_LEVEL_DBFS = -18.0
ABORT_GROWTH_DB = 12.0
RAMP_START_DBFS = -90.0
RAMP_END_DBFS = -60.0
RAMP_STEP_DB = 5.0


def evaluate_preflight(
    device: DeviceStatus,
    topology: AudioTopology,
    mixer: MixerState,
    software_loops: list[str],
    *,
    speakers_disconnected: bool = False,
    attenuation_confirmed: bool = False,
    baseline_peak_dbfs: float | None = None,
) -> SafetyState:
    reasons: list[str] = []
    if not device.connected:
        reasons.append("device is not connected")
    if device.usb_configuration != 2:
        reasons.append("USB Audio 2.0 configuration 2 is not selected")
    if not device.driver_bound:
        reasons.append("snd_usb_audio is not bound")
    if topology.playback_channels != 4 or topology.capture_channels != 6:
        reasons.append("expected 4-channel playback and 6-channel capture")
    if topology.explicit_feedback is not True:
        reasons.append("explicit feedback endpoint 0x85 is not confirmed")
    if software_loops:
        reasons.append("PipeWire/ALSA loopback route detected")
    direct_off = mixer.direct_monitor_enabled is False
    if not direct_off:
        reasons.append("DSP direct monitoring is not positively verified off")
    if not speakers_disconnected:
        reasons.append("speakers/headphones disconnection not confirmed")
    if not attenuation_confirmed:
        reasons.append("physical attenuation not confirmed")
    if baseline_peak_dbfs is None:
        reasons.append("capture baseline has not been measured")
    elif baseline_peak_dbfs >= ABORT_LEVEL_DBFS:
        reasons.append("capture baseline is already above the abort level")
    return SafetyState(
        software_loopback_detected=bool(software_loops),
        software_loopback_details=software_loops,
        direct_monitor_verified_off=direct_off,
        speakers_disconnected_confirmed=speakers_disconnected,
        attenuation_confirmed=attenuation_confirmed,
        baseline_peak_dbfs=baseline_peak_dbfs,
        safe_for_playback=not reasons,
        refusal_reasons=reasons,
    )


@dataclass(slots=True)
class RampGuard:
    abort_level_dbfs: float = ABORT_LEVEL_DBFS
    abort_growth_db: float = ABORT_GROWTH_DB
    previous_peak_dbfs: float | None = None

    def observe(self, peak_dbfs: float) -> str | None:
        if peak_dbfs >= self.abort_level_dbfs:
            return f"capture reached {peak_dbfs:.1f} dBFS (limit {self.abort_level_dbfs:.1f})"
        if (
            self.previous_peak_dbfs is not None
            and peak_dbfs - self.previous_peak_dbfs > self.abort_growth_db
        ):
            return (
                f"capture grew {peak_dbfs - self.previous_peak_dbfs:.1f} dB "
                f"between guard windows (limit {self.abort_growth_db:.1f})"
            )
        self.previous_peak_dbfs = peak_dbfs
        return None


def guarded_ramp_levels() -> list[float]:
    levels: list[float] = []
    value = RAMP_START_DBFS
    while value <= RAMP_END_DBFS:
        levels.append(value)
        value += RAMP_STEP_DB
    return levels


def playback_channel_plan() -> list[dict[str, object]]:
    return [
        {
            "channel": channel,
            "tone_hz": 1000 + channel * 250,
            "levels_dbfs": guarded_ramp_levels(),
            "guard_window_ms": 100,
            "abort_level_dbfs": ABORT_LEVEL_DBFS,
            "abort_growth_db": ABORT_GROWTH_DB,
        }
        for channel in range(1, 5)
    ]
