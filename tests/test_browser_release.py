from __future__ import annotations

import unittest
from unittest.mock import patch

from app.modules.system.browser_control_module import SystemBrowserControlModule
from app.pc_control.windows_input import WindowsInputError


class BrowserReleaseTests(unittest.TestCase):
    def test_success_reports_delivery_not_verified_browser_state(self):
        module = SystemBrowserControlModule()

        with (
            patch(
                "app.modules.system.browser_control_module._foreground_process_name",
                return_value="firefox.exe",
            ),
            patch(
                "app.modules.system.browser_control_module.send_hotkey",
                return_value=None,
            ) as hotkey,
        ):
            response = module.handle("открой новую вкладку")

        hotkey.assert_called_once_with(["ctrl", "t"])
        self.assertIn("Передала браузеру", response.text)
        self.assertIn("команд", response.text)
        self.assertNotIn("Открыла новую вкладку", response.text)

    def test_non_browser_foreground_blocks_hotkey(self):
        module = SystemBrowserControlModule()

        with (
            patch(
                "app.modules.system.browser_control_module._foreground_process_name",
                return_value="notepad.exe",
            ),
            patch("app.modules.system.browser_control_module.send_hotkey") as hotkey,
        ):
            response = module.handle("закрой вкладку")

        hotkey.assert_not_called()
        self.assertIn("не браузер", response.text)
        self.assertIn("notepad.exe", response.text)

    def test_windows_input_failure_never_reports_success(self):
        module = SystemBrowserControlModule()

        with (
            patch(
                "app.modules.system.browser_control_module._foreground_process_name",
                return_value="chrome.exe",
            ),
            patch(
                "app.modules.system.browser_control_module.send_hotkey",
                side_effect=WindowsInputError("SendInput rejected"),
            ),
        ):
            response = module.handle("закрой вкладку")

        self.assertIn("Не смогла", response.text)
        self.assertNotIn("Передала браузеру", response.text)

    def test_custom_browser_trigger_is_used_by_real_execution_path(self):
        module = SystemBrowserControlModule()

        class FakeTriggerStore:
            def get_feature_groups(self, feature_id, defaults):
                groups = {
                    action_id: dict(group, triggers=list(group.get("triggers", [])))
                    for action_id, group in defaults.items()
                }
                groups["browser.new_tab"]["triggers"] = ["мой новый таб"]
                return groups

        module.set_trigger_store(FakeTriggerStore())

        with (
            patch(
                "app.modules.system.browser_control_module._foreground_process_name",
                return_value="firefox.exe",
            ),
            patch(
                "app.modules.system.browser_control_module.send_hotkey",
                return_value=None,
            ) as hotkey,
        ):
            response = module.handle("мой новый таб")

        hotkey.assert_called_once_with(["ctrl", "t"])
        self.assertIn("Передала браузеру", response.text)


if __name__ == "__main__":
    unittest.main()
