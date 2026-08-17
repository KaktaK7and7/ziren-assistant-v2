import unittest
from unittest.mock import patch

from app.modules.registry import create_default_registry
from app.modules.system.keyboard_module import (
    MAX_VIRTUAL_DESKTOPS,
    SystemKeyboardModule,
)
from app.modules.system.screenshot_module import SystemScreenshotModule


class VoiceControlRegressionTests(unittest.TestCase):
    def test_keyboard_accepts_enter_vosk_aliases(self):
        module = SystemKeyboardModule()
        for phrase in (
            "нажми интер",
            "интер",
            "нажми ентер",
            "нажми энтэр",
        ):
            action = module._find_action(phrase)
            self.assertIsNotNone(action, phrase)
            self.assertEqual(action[0], "enter", phrase)

    def test_keyboard_accepts_tab_vosk_misrecognition(self):
        module = SystemKeyboardModule()
        action = module._find_action("нажми этап")
        self.assertIsNotNone(action)
        self.assertEqual(action[0], "tab")

    def test_virtual_desktop_parser_understands_numbered_desktops(self):
        module = SystemKeyboardModule()
        self.assertEqual(
            module._find_desktop_number("переключи меня на первый рабочий стол"),
            1,
        )
        self.assertEqual(
            module._find_desktop_number("переключи меня на второй рабочий стол"),
            2,
        )
        self.assertEqual(
            module._find_desktop_number("переключи на рабочий стол 3"),
            3,
        )

    def test_virtual_desktop_structured_action_is_absolute(self):
        module = SystemKeyboardModule()
        with patch("app.modules.system.keyboard_module.send_hotkey") as hotkey:
            response = module.execute_action(
                "keyboard.desktop_number",
                {"target": 2},
            )

        self.assertIsNotNone(response)
        self.assertIn("рабочий стол 2", response.text)
        self.assertEqual(hotkey.call_count, MAX_VIRTUAL_DESKTOPS + 1)
        self.assertEqual(
            hotkey.call_args_list[0].args[0],
            ["ctrl", "win", "left"],
        )
        self.assertEqual(
            hotkey.call_args_list[-1].args[0],
            ["ctrl", "win", "right"],
        )

    def test_old_desktop_phrase_maps_to_previous_desktop(self):
        module = SystemKeyboardModule()
        action = module._find_action("верни на старый рабочий стол")
        self.assertIsNotNone(action)
        self.assertEqual(action[0], "desktop_left")

    def test_screenshot_folder_phrase_has_safe_action(self):
        module = SystemScreenshotModule()
        phrase = "открой папку куда мы сохраняем скриншоты"
        self.assertTrue(module.can_handle(phrase))
        self.assertEqual(module._find_action(phrase), "screenshot.open_folder")

        with patch(
            "app.modules.system.screenshot_module.open_screenshot_directory"
        ) as open_folder:
            response = module.execute_action("screenshot.open_folder", {})

        open_folder.assert_called_once_with()
        self.assertEqual(response.text, "Открываю папку скриншотов.")

    def test_new_actions_are_exposed_to_melissa_catalog(self):
        registry = create_default_registry()
        by_feature = {
            item["feature_id"]: {
                action["action_id"]
                for action in item["actions"]
            }
            for item in registry.get_ai_capabilities()
        }
        self.assertIn("keyboard.desktop_number", by_feature["system.keyboard"])
        self.assertIn("screenshot.open_folder", by_feature["system.screenshot"])


if __name__ == "__main__":
    unittest.main()
