import inspect
import unittest
from unittest.mock import Mock, patch

from app.window_control import resolver as resolver_module
from app.window_control import windows_api
from app.window_control.models import WindowTarget
from app.window_control.resolver import WindowResolver


class WindowApiReleaseTests(unittest.TestCase):
    def test_close_window_uses_wm_close_and_never_process_kill(self):
        user32 = Mock()
        user32.IsWindow.return_value = 1
        user32.PostMessageW.return_value = 1

        with patch("app.window_control.windows_api._user32", return_value=user32):
            windows_api.close_window(123)

        user32.PostMessageW.assert_called_once_with(123, windows_api.WM_CLOSE, 0, 0)
        self.assertNotIn("force_close_process", inspect.getsource(resolver_module.WindowResolver.perform))

    def test_close_window_never_reports_success_when_windows_rejects_message(self):
        user32 = Mock()
        user32.IsWindow.return_value = 1
        user32.PostMessageW.return_value = 0

        with patch("app.window_control.windows_api._user32", return_value=user32):
            with self.assertRaisesRegex(RuntimeError, "не приняла запрос"):
                windows_api.close_window(321)

    def test_stale_window_handle_is_rejected_before_action(self):
        user32 = Mock()
        user32.IsWindow.return_value = 0

        with patch("app.window_control.windows_api._user32", return_value=user32):
            with self.assertRaisesRegex(RuntimeError, "больше недоступно"):
                windows_api.minimize_window(999)

        user32.ShowWindow.assert_not_called()

    def test_restore_requires_foreground_focus_instead_of_false_success(self):
        user32 = Mock()
        user32.IsWindow.return_value = 1
        user32.SetForegroundWindow.return_value = 0

        with patch("app.window_control.windows_api._user32", return_value=user32):
            with self.assertRaisesRegex(RuntimeError, "не разрешила переключить"):
                windows_api.restore_window(77)

        user32.ShowWindow.assert_called_once_with(77, windows_api.SW_RESTORE)
        user32.SetForegroundWindow.assert_called_once_with(77)

    def test_show_desktop_uses_whitelisted_sendinput_hotkey(self):
        with patch("app.window_control.windows_api.send_hotkey") as hotkey:
            windows_api.show_desktop()

        hotkey.assert_called_once_with(["win", "d"])
        self.assertNotIn("subprocess", windows_api.__dict__)


class WindowResolverReleaseTests(unittest.TestCase):
    @staticmethod
    def _resolver() -> WindowResolver:
        app_cache = Mock()
        app_cache.get_alias.return_value = None
        app_cache.load.return_value = {"targets": {}}
        return WindowResolver(app_cache=app_cache)

    def test_close_action_posts_close_only_after_unambiguous_resolution(self):
        target = WindowTarget(
            hwnd=42,
            title="Блокнот",
            process_id=100,
            process_name="notepad.exe",
        )
        resolver = self._resolver()

        with (
            patch("app.window_control.resolver.list_windows", return_value=[target]),
            patch("app.window_control.resolver.close_window") as close_window,
        ):
            result = resolver.perform("close", "блокнот")

        self.assertEqual(result.status, "success")
        self.assertEqual(result.target, target)
        close_window.assert_called_once_with(42)

    def test_ambiguous_resolution_performs_no_physical_action(self):
        first = WindowTarget(1, "Project Alpha", 10, "code.exe")
        second = WindowTarget(2, "Project Beta", 11, "code.exe")
        resolver = self._resolver()

        with (
            patch("app.window_control.resolver.list_windows", return_value=[first, second]),
            patch("app.window_control.resolver.close_window") as close_window,
        ):
            result = resolver.perform("close", "code")

        self.assertEqual(result.status, "ambiguous")
        close_window.assert_not_called()


if __name__ == "__main__":
    unittest.main()
