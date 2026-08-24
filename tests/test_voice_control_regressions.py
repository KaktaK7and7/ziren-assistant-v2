import unittest
from unittest.mock import patch

from app.modules.registry import create_default_registry
from app.modules.system.keyboard_module import (
    MAX_VIRTUAL_DESKTOPS,
    SystemKeyboardModule,
)
from app.modules.system.screen_recording_module import SystemScreenRecordingModule
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

    def test_keyboard_core_alias_matrix(self):
        module = SystemKeyboardModule()
        cases = {
            "нажми этап": "tab",
            "нажми тэб": "tab",
            "нажми ескейп": "escape",
            "нажми бек спейс": "backspace",
            "нажми дэлит": "delete",
            "нажми спейс": "space",
            "нажми хоум": "home",
            "нажми энд": "end",
            "нажми пейдж ап": "pageup",
            "нажми пейдж даун": "pagedown",
            "нажми стрелку вверх": "up",
            "нажми стрелку вниз": "down",
            "нажми стрелку влево": "left",
            "нажми стрелку вправо": "right",
        }
        for phrase, expected_action in cases.items():
            with self.subTest(phrase=phrase):
                action = module._find_action(phrase)
                self.assertIsNotNone(action)
                self.assertEqual(action[0], expected_action)

    def test_function_keys_f1_through_f12_are_voice_addressable(self):
        module = SystemKeyboardModule()
        for number in range(1, 13):
            for phrase in (f"нажми f{number}", f"нажми эф {number}"):
                with self.subTest(phrase=phrase):
                    action = module._find_action(phrase)
                    self.assertIsNotNone(action)
                    self.assertEqual(action[0], f"f{number}")
                    self.assertEqual(action[1], [f"f{number}"])

    def test_virtual_desktop_parser_understands_numbered_desktops(self):
        module = SystemKeyboardModule()
        cases = {
            "переключи меня на первый рабочий стол": 1,
            "переключи меня на второй рабочий стол": 2,
            "переключи на рабочий стол 3": 3,
            "переключи на одиннадцатый рабочий стол": 11,
            "переключи на двадцатый рабочий стол": 20,
        }
        for phrase, expected in cases.items():
            with self.subTest(phrase=phrase):
                self.assertEqual(module._find_desktop_number(phrase), expected)

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

    def test_close_virtual_desktop_has_explicit_safe_hotkey(self):
        module = SystemKeyboardModule()
        action = module._find_action("закрой текущий рабочий стол")
        self.assertIsNotNone(action)
        self.assertEqual(action[0], "close_desktop")
        self.assertEqual(action[1], ["ctrl", "win", "f4"])

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

    def test_recording_folder_phrase_has_safe_action(self):
        module = SystemScreenRecordingModule()
        phrase = "открой папку с записями экрана"
        self.assertTrue(module.can_handle(phrase))
        self.assertEqual(
            module._find_action(phrase),
            "screen_recording.open_folder",
        )

        with patch(
            "app.modules.system.screen_recording_module.open_recording_directory"
        ) as open_folder:
            response = module.execute_action("screen_recording.open_folder", {})

        open_folder.assert_called_once_with()
        self.assertEqual(response.text, "Открываю папку записей экрана.")

    def test_new_actions_are_exposed_to_melissa_catalog(self):
        registry = create_default_registry()
        by_feature = {
            item["feature_id"]: {
                action["action_id"]
                for action in item["actions"]
            }
            for item in registry.get_ai_capabilities()
        }
        keyboard_actions = by_feature["system.keyboard"]
        self.assertIn("keyboard.desktop_number", keyboard_actions)
        self.assertIn("keyboard.close_desktop", keyboard_actions)
        self.assertIn("keyboard.home", keyboard_actions)
        self.assertIn("keyboard.pagedown", keyboard_actions)
        self.assertIn("keyboard.f1", keyboard_actions)
        self.assertIn("keyboard.f12", keyboard_actions)
        self.assertIn("screenshot.open_folder", by_feature["system.screenshot"])
        self.assertIn(
            "screen_recording.open_folder",
            by_feature["system.screen_recording"],
        )


if __name__ == "__main__":
    unittest.main()
