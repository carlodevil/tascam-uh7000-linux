"""Per-user D-Bus service for serialized UH-7000 state and controls."""

from __future__ import annotations

import asyncio
import json
import logging
import signal
from typing import Any

from .controller import Controller, UnverifiedControlError

BUS_NAME = "io.github.carlodevil.UH7000.Control1"
OBJECT_PATH = "/io/github/carlodevil/UH7000/Control1"
INTERFACE_NAME = BUS_NAME
LOG = logging.getLogger("uh7000d")


async def run_service() -> None:
    try:
        from dbus_next.aio import MessageBus
        from dbus_next.service import ServiceInterface, method, signal as dbus_signal
    except ImportError as exc:
        raise SystemExit("uh7000d requires python3-dbus-next") from exc

    controller = Controller()

    class ControlInterface(ServiceInterface):
        def __init__(self) -> None:
            super().__init__(INTERFACE_NAME)

        @method()
        def GetState(self) -> "s":  # type: ignore[valid-type]
            return json.dumps(controller.snapshot(), sort_keys=True)

        @method()
        def GetDiagnostics(self) -> "s":  # type: ignore[valid-type]
            return json.dumps(controller.diagnostics(), sort_keys=True)

        @method()
        def ApplyMixerPatch(self, patch_json: "s") -> "s":  # type: ignore[valid-type]
            try:
                patch: dict[str, Any] = json.loads(patch_json)
                state = controller.apply_mixer_patch(patch)
            except (ValueError, TypeError, UnverifiedControlError) as exc:
                self.SafetyAbort(str(exc))
                raise
            payload = json.dumps(state.to_dict(), sort_keys=True)
            self.StateChanged(payload)
            return payload

        @method()
        def SetClockSource(
            self, source: "s", outputs_disconnected: "b"
        ) -> "s":  # type: ignore[valid-type]
            try:
                state = controller.set_clock_source(
                    source, outputs_disconnected=outputs_disconnected
                )
            except (OSError, RuntimeError, ValueError, UnverifiedControlError) as exc:
                self.SafetyAbort(str(exc))
                raise
            payload = json.dumps(state.to_dict(), sort_keys=True)
            self.StateChanged(payload)
            return payload

        @method()
        def Reset(self) -> "b":  # type: ignore[valid-type]
            try:
                controller.reset()
            except UnverifiedControlError as exc:
                self.SafetyAbort(str(exc))
                raise
            return False

        @method()
        def ApplyPreset(self, name: "s") -> "b":  # type: ignore[valid-type]
            try:
                controller.apply_preset(name)
            except (ValueError, UnverifiedControlError) as exc:
                self.SafetyAbort(str(exc))
                raise
            return False

        @method()
        def PlaybackPlan(self) -> "s":  # type: ignore[valid-type]
            return json.dumps(controller.playback_plan(), sort_keys=True)

        @dbus_signal()
        def ConnectionChanged(self, connected: "b") -> "b":  # type: ignore[valid-type]
            return connected

        @dbus_signal()
        def StateChanged(self, state_json: "s") -> "s":  # type: ignore[valid-type]
            return state_json

        @dbus_signal()
        def LevelMeters(self, levels_json: "s") -> "s":  # type: ignore[valid-type]
            return levels_json

        @dbus_signal()
        def DigitalClockValidityChanged(self, valid: "b") -> "b":  # type: ignore[valid-type]
            return valid

        @dbus_signal()
        def PassthroughChanged(self, enabled: "b") -> "b":  # type: ignore[valid-type]
            return enabled

        @dbus_signal()
        def PanelRequested(self) -> "":  # type: ignore[valid-type]
            return None

        @dbus_signal()
        def SafetyAbort(self, reason: "s") -> "s":  # type: ignore[valid-type]
            return reason

    bus = await MessageBus().connect()
    interface = ControlInterface()
    bus.export(OBJECT_PATH, interface)
    await bus.request_name(BUS_NAME)
    LOG.info("serving %s at %s", BUS_NAME, OBJECT_PATH)

    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, stopped.set)
        except (NotImplementedError, RuntimeError):
            pass

    previous_connected: bool | None = None

    async def poll() -> None:
        nonlocal previous_connected
        while not stopped.is_set():
            connected = bool(controller.snapshot()["device"]["connected"])
            if previous_connected is not None and connected != previous_connected:
                interface.ConnectionChanged(connected)
                interface.StateChanged(json.dumps(controller.snapshot(), sort_keys=True))
            previous_connected = connected
            try:
                await asyncio.wait_for(stopped.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

    task = asyncio.create_task(poll())
    await stopped.wait()
    task.cancel()
    bus.disconnect()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    try:
        asyncio.run(run_service())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
