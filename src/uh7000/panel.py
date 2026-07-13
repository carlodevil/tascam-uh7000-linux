"""Qt Quick control panel launcher."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .controller import Controller


def main() -> int:
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    try:
        from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot, QUrl
        from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtQml import QQmlApplicationEngine
    except ImportError as exc:
        raise SystemExit(f"uh7000-panel is missing a PySide6 Qt module: {exc}") from exc

    class PanelBackend(QObject):
        changed = Signal()

        def __init__(self) -> None:
            super().__init__()
            self.controller = Controller()
            self.service = QDBusInterface(
                "io.github.carlodevil.UH7000.Control1",
                "/io/github/carlodevil/UH7000/Control1",
                "io.github.carlodevil.UH7000.Control1",
                QDBusConnection.sessionBus(),
            )
            self._state: dict[str, object] = {}
            self._pipewire_command = self._find_pipewire_command()
            self._analog_playback_active = False
            self._analog_playback_status = "Analog playback inactive"
            self._refresh_analog_playback_status()
            self.refresh()

        @staticmethod
        def _find_pipewire_command() -> str | None:
            installed = shutil.which("uh7000-pipewire")
            if installed:
                return installed
            source_helper = Path(__file__).parent.parent / "tascam-uh7000-pipewire"
            if source_helper.is_file() and os.access(source_helper, os.X_OK):
                return str(source_helper)
            return None

        def _refresh_analog_playback_status(self) -> None:
            if self._pipewire_command is None:
                self._analog_playback_active = False
                self._analog_playback_status = "Analog playback helper unavailable"
                return
            result = subprocess.run(
                [self._pipewire_command, "status"],
                capture_output=True,
                check=False,
                text=True,
            )
            self._analog_playback_active = result.returncode == 0
            output = (result.stdout or result.stderr).strip()
            self._analog_playback_status = output or "Analog playback unavailable"

        def _set_analog_playback(self, command: str) -> None:
            if self._pipewire_command is None:
                self._analog_playback_status = "Analog playback helper unavailable"
                self.changed.emit()
                return
            result = subprocess.run(
                [self._pipewire_command, command],
                capture_output=True,
                check=False,
                text=True,
            )
            output = (result.stdout or result.stderr).strip()
            self._refresh_analog_playback_status()
            if result.returncode != 0:
                self._analog_playback_status = output or "Analog playback command failed"
            self.refresh()

        @Slot()
        def refresh(self) -> None:
            reply = self.service.call("GetState")
            if reply.type() != QDBusMessage.MessageType.ErrorMessage and reply.arguments():
                try:
                    self._state = json.loads(reply.arguments()[0])
                except (TypeError, ValueError):
                    self._state = self.controller.snapshot()
            else:
                self._state = self.controller.snapshot()
            self.changed.emit()

        @Slot(str, bool)
        def setClockSource(self, source: str, outputs_disconnected: bool) -> None:
            reply = self.service.call("SetClockSource", source, outputs_disconnected)
            if reply.type() != QDBusMessage.MessageType.ErrorMessage and reply.arguments():
                try:
                    self._state["mixer"] = json.loads(reply.arguments()[0])
                except (TypeError, ValueError):
                    pass
            self.refresh()

        @Slot()
        def enableAnalogPlayback(self) -> None:
            self._set_analog_playback("enable")

        @Slot()
        def setAnalogPlaybackDefault(self) -> None:
            self._set_analog_playback("set-default")

        @Slot()
        def disableAnalogPlayback(self) -> None:
            self._set_analog_playback("disable")

        @Property(bool, notify=changed)
        def connected(self) -> bool:
            return bool(self._state.get("device", {}).get("connected", False))  # type: ignore[union-attr]

        @Property(bool, notify=changed)
        def safetyReady(self) -> bool:
            return bool(self._state.get("safety", {}).get("safe_for_playback", False))  # type: ignore[union-attr]

        @Property(bool, constant=True)
        def hardwareControlsVerified(self) -> bool:
            return False

        @Property(bool, notify=changed)
        def analogPlaybackActive(self) -> bool:
            return self._analog_playback_active

        @Property(str, notify=changed)
        def analogPlaybackStatus(self) -> str:
            return self._analog_playback_status

        @Property(str, notify=changed)
        def clockSource(self) -> str:
            return str(self._state.get("mixer", {}).get("clock_source", "automatic"))  # type: ignore[union-attr]

        @Property(str, notify=changed)
        def statusText(self) -> str:
            device = self._state.get("device", {})
            if not device.get("connected", False):  # type: ignore[union-attr]
                return "UH-7000 disconnected"
            return "UH-7000 · UAC2 config %s · %s" % (
                device.get("usb_configuration", "?"),  # type: ignore[union-attr]
                "snd_usb_audio ready" if device.get("driver_bound") else "driver not bound",  # type: ignore[union-attr]
            )

        @Property(str, notify=changed)
        def stateJson(self) -> str:
            return json.dumps(self._state, sort_keys=True)

    app = QGuiApplication(sys.argv)
    app.setApplicationName("UH-7000 Control")
    app.setOrganizationName("carlodevil")
    backend = PanelBackend()
    # Keep the context object alive until after QML has been torn down.
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("uh7000", backend)
    qml_path = Path(__file__).with_name("qml") / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_path)))
    if not engine.rootObjects():
        return 1
    timer = QTimer()
    timer.setInterval(1000)
    timer.timeout.connect(backend.refresh)
    timer.start()
    screenshot_path = os.environ.get("UH7000_PANEL_TEST_SCREENSHOT")
    if screenshot_path:

        def capture(
            engine: QQmlApplicationEngine = engine,
            screenshot_path: str = screenshot_path,
        ) -> None:
            root = engine.rootObjects()[0]
            root.screen().grabWindow(root.winId()).save(screenshot_path)

        QTimer.singleShot(400, capture)
    test_exit_ms = int(os.environ.get("UH7000_PANEL_TEST_EXIT_MS", "0"))
    if test_exit_ms > 0:
        QTimer.singleShot(test_exit_ms, app.quit)
    exit_code = app.exec()
    timer.stop()
    # Destroy QML before the Python context object falls out of scope.
    del engine
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
