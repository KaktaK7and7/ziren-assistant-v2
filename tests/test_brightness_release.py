import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.modules.system.brightness_module import SystemBrightnessModule
from app.pc_control import brightness
from app.pc_control.brightness import BrightnessControlError


class BrightnessReleaseTests(unittest.TestCase):
    @staticmethod
    def _dxva_with_readings(*percentages: int):
        dxva2 = Mock()
        readings = iter(percentages)

        def get_brightness(_handle, minimum, current, maximum):
            try:
                value = next(readings)
            except StopIteration:
                value = percentages[-1]
            minimum._obj.value = 0
            current._obj.value = value
            maximum._obj.value = 100
            return 1

        dxva2.GetMonitorBrightness.side_effect = get_brightness
        dxva2.SetMonitorBrightness.return_value = 1
        return dxva2

    def test_set_brightness_reports_success_only_after_readback_matches(self):
        monitor = SimpleNamespace(hPhysicalMonitor=101, szPhysicalMonitorDescription="Test")
        dxva2 = self._dxva_with_readings(20, 40)

        with (
            patch("app.pc_control.brightness._physical_monitors", return_value=[monitor]),
            patch("app.pc_control.brightness._destroy"),
            patch("app.pc_control.brightness._dxva2", return_value=dxva2),
            patch("app.pc_control.brightness.time.sleep"),
        ):
            changed = brightness.set_brightness(40, 1)

        self.assertEqual(changed, [1])
        dxva2.SetMonitorBrightness.assert_called_once_with(101, 40)

    def test_ddc_success_without_actual_change_is_not_false_success(self):
        monitor = SimpleNamespace(hPhysicalMonitor=202, szPhysicalMonitorDescription="Test")
        dxva2 = self._dxva_with_readings(20, 20, 20, 20, 20, 20, 20)

        with (
            patch("app.pc_control.brightness._physical_monitors", return_value=[monitor]),
            patch("app.pc_control.brightness._destroy"),
            patch("app.pc_control.brightness._dxva2", return_value=dxva2),
            patch("app.pc_control.brightness.time.sleep"),
        ):
            with self.assertRaisesRegex(BrightnessControlError, "не подтвердилось"):
                brightness.set_brightness(70, 1)

    def test_tiny_monitor_rounding_difference_is_accepted(self):
        monitor = SimpleNamespace(hPhysicalMonitor=303, szPhysicalMonitorDescription="Test")
        dxva2 = self._dxva_with_readings(10, 48)

        with (
            patch("app.pc_control.brightness._physical_monitors", return_value=[monitor]),
            patch("app.pc_control.brightness._destroy"),
            patch("app.pc_control.brightness._dxva2", return_value=dxva2),
            patch("app.pc_control.brightness.time.sleep"),
        ):
            changed = brightness.set_brightness(50, 1)

        self.assertEqual(changed, [1])

    def test_module_keeps_ddc_failure_honest(self):
        module = SystemBrightnessModule()
        with patch(
            "app.modules.system.brightness_module.set_brightness",
            side_effect=BrightnessControlError("изменение яркости не подтвердилось"),
        ):
            response = module.execute_action(
                "brightness.set",
                {"percent": 40, "monitor": 2},
            )

        self.assertIn("не подтвердилось", response.text)
        self.assertNotIn("Установила", response.text)


if __name__ == "__main__":
    unittest.main()
