import unittest
from pathlib import Path

from app.modules.system.browser_control_module import SystemBrowserControlModule
from app.modules.system.clipboard_module import SystemClipboardModule
from app.modules.system.file_navigation_module import SystemFileNavigationModule
from app.modules.system.keyboard_module import SystemKeyboardModule
from app.modules.system.screenshot_module import SystemScreenshotModule
from app.modules.system.text_input_module import SystemTextInputModule
from app.pc_control.file_navigation import is_safe_to_open


class PcControlRoutingTests(unittest.TestCase):
    def test_browser_commands_are_specific(self) -> None:
        module = SystemBrowserControlModule()
        self.assertTrue(module.can_handle("открой новую вкладку"))
        self.assertTrue(module.can_handle("обнови страницу"))
        self.assertFalse(module.can_handle("открой дискорд"))

    def test_keyboard_hotkeys_are_whitelisted_phrases(self) -> None:
        module = SystemKeyboardModule()
        self.assertTrue(module.can_handle("выдели всё"))
        self.assertTrue(module.can_handle("нажми enter"))
        self.assertFalse(module.can_handle("запусти powershell и нажми что угодно"))

    def test_text_input_requires_explicit_local_prefix(self) -> None:
        module = SystemTextInputModule()
        self.assertTrue(module.can_handle("напечатай привет мир"))
        self.assertTrue(module.can_handle("введи текст тестовая строка"))
        self.assertFalse(module.can_handle("напиши диане привет"))

    def test_clipboard_does_not_claim_social_send(self) -> None:
        module = SystemClipboardModule()
        self.assertTrue(module.can_handle("что скопировано"))
        self.assertTrue(module.can_handle("скопируй текст привет"))
        self.assertFalse(module.can_handle("отправь скопированное сообщение диане"))

    def test_screenshot_send_is_left_for_social_module(self) -> None:
        module = SystemScreenshotModule()
        self.assertTrue(module.can_handle("сделай скриншот"))
        self.assertFalse(module.can_handle("сделай скриншот и отправь диане"))

    def test_file_navigation_claims_known_folders_before_app_launcher(self) -> None:
        module = SystemFileNavigationModule()
        self.assertTrue(module.can_handle("открой загрузки"))
        self.assertTrue(module.can_handle("открой проводник"))
        self.assertTrue(module.can_handle("покажи последний скачанный файл"))
        self.assertTrue(module.can_handle("открой последний скачанный файл"))
        self.assertFalse(module.can_handle("открой дискорд"))

    def test_download_opening_uses_allowlist_not_executable_blacklist(self) -> None:
        self.assertTrue(is_safe_to_open(Path("report.pdf")))
        self.assertTrue(is_safe_to_open(Path("model.blend")))
        self.assertTrue(is_safe_to_open(Path("archive.zip")))
        self.assertFalse(is_safe_to_open(Path("installer.exe")))
        self.assertFalse(is_safe_to_open(Path("script.py")))
        self.assertFalse(is_safe_to_open(Path("launch.jar")))
        self.assertFalse(is_safe_to_open(Path("unknown.custom")))


if __name__ == "__main__":
    unittest.main()
