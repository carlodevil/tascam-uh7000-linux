"""Typed public state for the UH-7000 service."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class StringEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class MixerMode(StringEnum):
    MULTITRACK = "multitrack"
    STEREO_MIX = "stereo-mix"


class ClockSource(StringEnum):
    AUTOMATIC = "automatic"
    INTERNAL = "internal"
    DIGITAL = "digital-input"


class LatencyProfile(StringEnum):
    SAFE = "safe"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    LOWEST = "lowest"


class EffectKind(StringEnum):
    OFF = "off"
    COMPRESSOR = "compressor"
    NOISE_SUPPRESSOR = "noise-suppressor"
    DE_ESSER = "de-esser"
    EXCITER = "exciter"
    EQ = "eq"
    LIMITER_LOW_CUT = "limiter-low-cut"


@dataclass(slots=True)
class JsonState:
    def to_dict(self) -> dict[str, Any]:
        def convert(value: Any) -> Any:
            if isinstance(value, Enum):
                return value.value
            if isinstance(value, JsonState):
                return value.to_dict()
            if isinstance(value, list):
                return [convert(item) for item in value]
            if isinstance(value, dict):
                return {key: convert(item) for key, item in value.items()}
            return value

        return {key: convert(value) for key, value in asdict(self).items()}


@dataclass(slots=True)
class DeviceStatus(JsonState):
    connected: bool = False
    sysfs_path: str | None = None
    bus_number: int | None = None
    device_number: int | None = None
    usb_configuration: int | None = None
    usb_speed_mbps: int | None = None
    firmware_version: str | None = None
    driver_bound: bool = False
    package_version: str = "0.2.0b20"
    error: str | None = None


@dataclass(slots=True)
class AudioTopology(JsonState):
    playback_channels: int = 4
    capture_channels: int = 6
    sample_format: str = "S24_3LE"
    sample_rates: list[int] = field(
        default_factory=lambda: [44100, 48000, 88200, 96000, 176400, 192000]
    )
    feedback_endpoint: str = "0x85"
    explicit_feedback: bool | None = None
    physical_input_labels: list[str] = field(
        default_factory=lambda: ["Analog 1", "Analog 2", "AES/EBU 1", "AES/EBU 2"]
    )
    dsp_capture_labels: list[str] = field(
        default_factory=lambda: ["DSP/Master L (unverified)", "DSP/Master R (unverified)"]
    )
    mapping_verified: bool = False
    alsa_card: str | None = None


@dataclass(slots=True)
class ChannelState(JsonState):
    name: str
    fader_db: float = 0.0
    pan: int = 0
    muted: bool = False
    soloed: bool = False
    linked: bool = False
    send_level: int = 0
    send_pre: bool = False

    def validate(self) -> None:
        if not -127.0 <= self.fader_db <= 12.0:
            raise ValueError(f"{self.name}: fader must be between -127 and +12 dB")
        if not -15 <= self.pan <= 15:
            raise ValueError(f"{self.name}: pan must be between -15 and +15")
        if not 0 <= self.send_level <= 127:
            raise ValueError(f"{self.name}: send must be between 0 and 127")


def default_channels() -> list[ChannelState]:
    return [
        ChannelState(name=name)
        for name in (
            "Analog 1",
            "Analog 2",
            "Digital 1",
            "Digital 2",
            "Computer 1",
            "Computer 2",
            "Computer 3",
            "Computer 4",
        )
    ]


@dataclass(slots=True)
class MixerState(JsonState):
    mode: MixerMode = MixerMode.MULTITRACK
    clock_source: ClockSource = ClockSource.AUTOMATIC
    latency_profile: LatencyProfile = LatencyProfile.NORMAL
    monitor_mix: float = 0.5
    direct_monitor_enabled: bool | None = None
    auto_power_save: bool = True
    line_output_source: str = "master"
    digital_output_source: str = "analog-1-2"
    digital_output_format: str = "aes-ebu"
    master_fader_db: float = 0.0
    channels: list[ChannelState] = field(default_factory=default_channels)
    verified_controls: list[str] = field(default_factory=list)

    def validate(self) -> None:
        if not 0.0 <= self.monitor_mix <= 1.0:
            raise ValueError("monitor mix must be between 0 and 1")
        if not -127.0 <= self.master_fader_db <= 12.0:
            raise ValueError("master fader must be between -127 and +12 dB")
        if len(self.channels) != 8:
            raise ValueError("the UH-7000 mixer must have eight input channels")
        for channel in self.channels:
            channel.validate()


@dataclass(slots=True)
class EffectsState(JsonState):
    dynamics: EffectKind = EffectKind.OFF
    dynamics_enabled: bool = False
    dynamics_target: str | None = None
    parameters: dict[str, float | int | str] = field(default_factory=dict)
    reverb_enabled: bool = False
    reverb_type: str = "hall"
    reverb_pre_delay_ms: int = 42
    reverb_time_seconds: float = 2.7
    sample_rate: int = 48000
    verified: bool = False

    def validate(self) -> None:
        if self.reverb_type not in {"hall", "room", "live", "studio", "plate"}:
            raise ValueError("unsupported reverb type")
        if not 0 <= self.reverb_pre_delay_ms <= 100:
            raise ValueError("reverb pre-delay must be between 0 and 100 ms")
        if not 0.1 <= self.reverb_time_seconds <= 10.0:
            raise ValueError("reverb time must be between 0.1 and 10 seconds")
        if self.sample_rate >= 176400 and (self.dynamics_enabled or self.reverb_enabled):
            raise ValueError("effects are unavailable at 176.4/192 kHz")
        if self.sample_rate >= 88200 and self.dynamics_enabled and self.reverb_enabled:
            raise ValueError("only one effect family is available at 88.2/96 kHz")


@dataclass(slots=True)
class SafetyState(JsonState):
    software_loopback_detected: bool = False
    software_loopback_details: list[str] = field(default_factory=list)
    direct_monitor_verified_off: bool = False
    speakers_disconnected_confirmed: bool = False
    attenuation_confirmed: bool = False
    baseline_peak_dbfs: float | None = None
    safe_for_playback: bool = False
    refusal_reasons: list[str] = field(default_factory=list)
    last_abort_reason: str | None = None


def adc_preset() -> tuple[MixerState, EffectsState]:
    mixer = MixerState(
        monitor_mix=0.0,
        line_output_source="master",
        digital_output_source="analog-1-2",
    )
    for channel in mixer.channels:
        channel.fader_db = -127.0 if channel.name.startswith("Computer") else 0.0
    return mixer, EffectsState()


def adcdac_preset() -> tuple[MixerState, EffectsState]:
    mixer = MixerState(
        monitor_mix=0.5,
        line_output_source="digital-1-2",
        digital_output_source="analog-1-2",
    )
    return mixer, EffectsState()
