"""Qt Quick control panel launcher."""

from __future__ import annotations

import json
import os
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

        @Property(bool, notify=changed)
        def connected(self) -> bool:
            return bool(self._state.get("device", {}).get("connected", False))  # type: ignore[union-attr]

        @Property(bool, notify=changed)
        def safetyReady(self) -> bool:
            return bool(self._state.get("safety", {}).get("safe_for_playback", False))  # type: ignore[union-attr]

        @Property(bool, constant=True)
        def hardwareControlsVerified(self) -> bool:
            return False

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
    engine = QQmlApplicationEngine()
    backend = PanelBackend()
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

        def capture() -> None:
            root = engine.rootObjects()[0]
            root.screen().grabWindow(root.winId()).save(screenshot_path)

        QTimer.singleShot(400, capture)
    test_exit_ms = int(os.environ.get("UH7000_PANEL_TEST_EXIT_MS", "0"))
    if test_exit_ms > 0:
        QTimer.singleShot(test_exit_ms, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
