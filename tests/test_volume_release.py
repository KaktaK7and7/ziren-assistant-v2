import unittest
from unittest.mock import Mock, patch

from app.modules.system.volume_module import SystemVolumeModule


class VolumeReleaseTests(unittest.TestCase):
    def test_set_volume_requires_readback_match(self):
        module = SystemVolumeModule()
        volume = Mock()
        volume.GetMasterVolumeLevelScalar.return_value = 0.40
        volume.GetMute.return_value = 0

        actual = module._set_volume_percent(volume, 40)

        self.assertEqual(actual, 40)
        volume.SetMute.assert_called_once_with(0, None)
        volume.SetMasterVolumeLevelScalar.assert_called_once_with(0.40, None)

    def test_set_volume_rejects_false_success_from_endpoint(self):
        module = SystemVolumeModule()
        volume = Mock()
        volume.GetMasterVolumeLevelScalar.return_value = 0.20
        volume.GetMute.return_value = 0

        with self.assertRaisesRegex(RuntimeError, "не подтвердила громкость"):
            module._set_volume_percent(volume, 70)

    def test_set_volume_requires_endpoint_to_be_unmuted(self):
        module = SystemVolumeModule()
        volume = Mock()
        volume.GetMasterVolumeLevelScalar.return_value = 0.50
        volume.GetMute.return_value = 1

        with self.assertRaisesRegex(RuntimeError, "оставила системный звук в mute"):
            module._set_volume_percent(volume, 50)

    def test_mute_and_unmute_are_verified(self):
        module = SystemVolumeModule()
        volume = Mock()
        volume.GetMute.return_value = 1
        module._set_mute(volume, True)
        volume.SetMute.assert_called_with(1, None)

        volume.reset_mock()
        volume.GetMute.return_value = 0
        module._set_mute(volume, False)
        volume.SetMute.assert_called_with(0, None)

    def test_mute_false_success_is_rejected(self):
        module = SystemVolumeModule()
        volume = Mock()
        volume.GetMute.return_value = 0

        with self.assertRaisesRegex(RuntimeError, "не подтвердила состояние mute"):
            module._set_mute(volume, True)

    def test_missing_audio_endpoint_never_speaks_success(self):
        module = SystemVolumeModule()
        with patch.object(
            module,
            "_get_volume",
            side_effect=RuntimeError("нет активного устройства вывода"),
        ):
            response = module.execute_action("volume.set", {"percent": 30})

        self.assertIn("Не смогла изменить громкость", response.text)
        self.assertNotIn("Громкость установлена", response.text)

    def test_volume_response_uses_actual_readback_value(self):
        module = SystemVolumeModule()
        volume = Mock()
        with (
            patch.object(module, "_get_volume", return_value=volume),
            patch.object(module, "_set_volume_percent", return_value=39),
        ):
            response = module.execute_action("volume.set", {"percent": 40})

        self.assertEqual(response.text, "Громкость установлена на 39 процентов.")


if __name__ == "__main__":
    unittest.main()
