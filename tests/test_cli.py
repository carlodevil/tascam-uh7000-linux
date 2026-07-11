from __future__ import annotations

import contextlib
import io
import json
import unittest

from uh7000.cli import main


class CliTests(unittest.TestCase):
    def invoke(self, *arguments: str) -> tuple[int, object]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(list(arguments))
        return code, json.loads(output.getvalue())

    def test_playback_plan_is_dry_run(self) -> None:
        code, payload = self.invoke("--json", "playback-plan")
        self.assertEqual(0, code)
        self.assertEqual(4, len(payload))

    def test_preflight_fails_closed_without_hardware(self) -> None:
        code, payload = self.invoke("--json", "preflight")
        self.assertEqual(78, code)
        self.assertFalse(payload["safe_for_playback"])

    def test_state_schema(self) -> None:
        code, payload = self.invoke("--json", "state")
        self.assertEqual(0, code)
        self.assertEqual("io.github.carlodevil.UH7000.State.v1", payload["schema"])


if __name__ == "__main__":
    unittest.main()
