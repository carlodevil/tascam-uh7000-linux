"""ALSA and PipeWire topology discovery without opening audio streams."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from .models import AudioTopology


def find_alsa_card(cards_text: str) -> str | None:
    for line in cards_text.splitlines():
        if re.search(r"UH-?7000|TASCAM|TEAC", line, re.IGNORECASE):
            match = re.search(r"\[([^]]+)\]", line)
            return match.group(1).strip() if match else line.strip()
    return None


def parse_stream_topology(text: str) -> AudioTopology:
    topology = AudioTopology()
    playback = re.search(r"Playback:.*?(?=Capture:|$)", text, re.DOTALL | re.IGNORECASE)
    capture = re.search(r"Capture:.*", text, re.DOTALL | re.IGNORECASE)
    if playback:
        channels = re.search(r"Channels:\s*(\d+)", playback.group(0), re.IGNORECASE)
        if channels:
            topology.playback_channels = int(channels.group(1))
        topology.explicit_feedback = bool(
            re.search(r"Sync Endpoint:\s*0x85", playback.group(0), re.IGNORECASE)
            and re.search(r"Implicit Feedback Mode:\s*No", playback.group(0), re.IGNORECASE)
        )
    if capture:
        channels = re.search(r"Channels:\s*(\d+)", capture.group(0), re.IGNORECASE)
        if channels:
            topology.capture_channels = int(channels.group(1))
    rates = sorted(
        {int(value) for value in re.findall(r"\b(?:44100|48000|88200|96000|176400|192000)\b", text)}
    )
    if rates:
        topology.sample_rates = rates
    format_match = re.search(r"Format:\s*([A-Z0-9_]+)", text)
    if format_match:
        topology.sample_format = format_match.group(1)
    return topology


def inspect_audio(proc_root: Path = Path("/proc/asound")) -> AudioTopology:
    topology = AudioTopology()
    try:
        cards_text = (proc_root / "cards").read_text(encoding="utf-8")
    except OSError:
        return topology
    topology.alsa_card = find_alsa_card(cards_text)
    if not topology.alsa_card:
        return topology
    for stream in proc_root.glob("card*/stream*"):
        try:
            text = stream.read_text(encoding="utf-8")
        except OSError:
            continue
        if re.search(r"UH-?7000|TASCAM|TEAC", text, re.IGNORECASE):
            parsed = parse_stream_topology(text)
            parsed.alsa_card = topology.alsa_card
            return parsed
    return topology


def pipewire_loopbacks(timeout: float = 2.0) -> list[str]:
    command = shutil.which("pw-link")
    if not command:
        return []
    try:
        result = subprocess.run(
            [command, "-l"],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    suspects: list[str] = []
    for index, line in enumerate(lines):
        context = " ".join(lines[max(0, index - 1) : index + 2])
        if re.search(r"loopback|monitor.*playback|capture.*playback", context, re.IGNORECASE):
            if context not in suspects:
                suspects.append(context)
    return suspects
