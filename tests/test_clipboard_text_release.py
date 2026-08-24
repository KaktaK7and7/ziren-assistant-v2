import unittest
from unittest.mock import patch

from app.modules.system.clipboard_module import SystemClipboardModule
from app.modules.system.text_input_module import SystemTextInputModule


class ClipboardReleaseTests(unittest.TestCase):
    def test_snake_clipboard_write_verifies_exact_content(self):
        module = SystemClipboardModule()
        with (
            patch("app.modules.system.clipboard_module.write_text") as write_text,
            patch("app.modules.system.clipboard_module.read_text", return_value="Привет, мир"),
        ):
            response = module.handle("скопируй текст Привет, мир")

        write_text.assert_called_once_with("Привет, мир")
        self.assertEqual(response.text, "Скопировала текст в буфер обмена.")

    def test_melissa_clipboard_write_uses_same_verified_path(self):
        module = SystemClipboardModule()
        with (
            patch("app.modules.system.clipboard_module.write_text") as write_text,
            patch("app.modules.system.clipboard_module.read_text", return_value="данные"),
        ):
            response = module.execute_action("clipboard.write", {"text": "данные"})

        write_text.assert_called_once_with("данные")
        self.assertEqual(response.text, "Скопировала текст в буфер обмена.")

    def test_clipboard_mismatch_never_reports_success(self):
        module = SystemClipboardModule()
        with (
            patch("app.modules.system.clipboard_module.write_text"),
            patch("app.modules.system.clipboard_module.read_text", return_value="другой текст"),
        ):
            response = module.execute_action("clipboard.write", {"text": "нужный текст"})

        self.assertIn("не совпало", response.text)
        self.assertNotIn("Скопировала текст", response.text)

    def test_social_clipboard_send_is_not_claimed_by_local_clipboard(self):
        module = SystemClipboardModule()
        self.assertFalse(module.can_handle("отправь скопированное сообщение диане"))
        self.assertFalse(module.can_handle("отправь то что в буфере диане"))


class TextInputReleaseTests(unittest.TestCase):
    def test_snake_and_melissa_use_same_unicode_backend(self):
        module = SystemTextInputModule()
        with patch("app.modules.system.text_input_module.type_unicode_text") as type_text:
            snake = module.handle("напечатай Привет 世界")
            melissa = module.execute_action("text.type", {"text": "Привет 世界"})

        self.assertEqual(type_text.call_count, 2)
        self.assertEqual(type_text.call_args_list[0].args[0], "Привет 世界")
        self.assertEqual(type_text.call_args_list[1].args[0], "Привет 世界")
        self.assertEqual(snake.text, "Передала текст в активное окно.")
        self.assertEqual(melissa.text, "Передала текст в активное окно.")

    def test_text_input_never_claims_target_application_accepted_text(self):
        module = SystemTextInputModule()
        with patch("app.modules.system.text_input_module.type_unicode_text"):
            response = module.execute_action("text.type", {"text": "тест"})

        self.assertNotEqual(response.text, "Напечатала.")
        self.assertIn("Передала", response.text)


if __name__ == "__main__":
    unittest.main()
