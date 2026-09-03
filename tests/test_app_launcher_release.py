from __future__ import annotations

import unittest
from unittest.mock import patch

from app.app_launcher.launcher import AppLauncher
from app.app_launcher.models import AppTarget


class AppLauncherReleaseTests(unittest.TestCase):
    def test_system_url_requires_browser_handoff_confirmation(self):
        launcher = AppLauncher()
        target = AppTarget(
            target_id="web:test",
            name="Test Web App",
            type="system",
            launch_uri="https://example.com",
        )

        with patch("app.app_launcher.launcher.webbrowser.open", return_value=False):
            with self.assertRaises(RuntimeError):
                launcher.launch(target)

    def test_system_url_accepts_confirmed_browser_handoff(self):
        launcher = AppLauncher()
        target = AppTarget(
            target_id="web:test",
            name="Test Web App",
            type="system",
            launch_uri="https://example.com",
        )

        with patch("app.app_launcher.launcher.webbrowser.open", return_value=True) as opener:
            launcher.launch(target)

        opener.assert_called_once_with("https://example.com")

    def test_system_process_launch_never_uses_shell_true(self):
        launcher = AppLauncher()
        target = AppTarget(
            target_id="system:notepad",
            name="Notepad",
            type="system",
            path="notepad.exe",
        )

        with patch("app.app_launcher.launcher.subprocess.Popen") as popen:
            launcher.launch(target)

        popen.assert_called_once_with(["notepad.exe"], shell=False)


if __name__ == "__main__":
    unittest.main()
