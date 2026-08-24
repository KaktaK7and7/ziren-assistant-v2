import unittest
from unittest.mock import Mock, patch

from app.modules.system.monitor_control_module import SystemMonitorControlModule
from app.pc_control.monitors import MonitorControlError, move_active_window


class MonitorMoveReleaseTests(unittest.TestCase):
    def test_move_is_successful_only_after_monitor_handle_changes(self):
        user32 = Mock()
        user32.GetSystemMetrics.return_value = 2
        user32.GetForegroundWindow.return_value = 100
        user32.IsWindow.return_value = 1
        user32.MonitorFromWindow.side_effect = [1, 2]

        with (
            patch("app.pc_control.monitors._user32", return_value=user32),
            patch("app.pc_control.monitors.send_hotkey") as hotkey,
            patch("app.pc_control.monitors.time.sleep"),
        ):
            move_active_window("right")

        hotkey.assert_called_once_with(["win", "shift", "right"])

    def test_one_monitor_fails_before_sending_hotkey(self):
        user32 = Mock()
        user32.GetSystemMetrics.return_value = 1

        with (
            patch("app.pc_control.monitors._user32", return_value=user32),
            patch("app.pc_control.monitors.send_hotkey") as hotkey,
        ):
            with self.assertRaisesRegex(MonitorControlError, "нужен второй"):
                move_active_window("left")

        hotkey.assert_not_called()

    def test_no_actual_monitor_change_is_not_reported_as_success(self):
        user32 = Mock()
        user32.GetSystemMetrics.return_value = 2
        user32.GetForegroundWindow.return_value = 100
        user32.IsWindow.return_value = 1
        user32.MonitorFromWindow.return_value = 1

        with (
            patch("app.pc_control.monitors._user32", return_value=user32),
            patch("app.pc_control.monitors.send_hotkey") as hotkey,
            patch("app.pc_control.monitors.time.sleep"),
        ):
            with self.assertRaisesRegex(MonitorControlError, "не подтвердился"):
                move_active_window("right")

        hotkey.assert_called_once_with(["win", "shift", "right"])

    def test_module_reports_success_only_after_verified_backend_success(self):
        module = SystemMonitorControlModule()
        with patch("app.modules.system.monitor_control_module.move_active_window") as move:
            response = module.execute_action("monitor.window_right", {})

        move.assert_called_once_with("right")
        self.assertEqual(response.text, "Перенесла активное окно на монитор справа.")

        with patch(
            "app.modules.system.monitor_control_module.move_active_window",
            side_effect=MonitorControlError("перенос не подтверждён"),
        ):
            response = module.execute_action("monitor.window_right", {})

        self.assertIn("Не смогла перенести окно", response.text)


if __name__ == "__main__":
    unittest.main()
