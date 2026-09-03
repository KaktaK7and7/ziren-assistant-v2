import base64
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app.modules.system.screen_recording_module import SystemScreenRecordingModule
from app.pc_control.screenshot import JPEG_PREFIX, ScreenshotError, save_capture
from app.vision.screen_capture import CapturedScreen


class ScreenshotReleaseTests(unittest.TestCase):
    @staticmethod
    def _jpeg_capture() -> CapturedScreen:
        buffer = io.BytesIO()
        Image.new("RGB", (16, 16), (20, 30, 40)).save(buffer, format="JPEG")
        payload = buffer.getvalue()
        return CapturedScreen(
            data_url=JPEG_PREFIX + base64.b64encode(payload).decode("ascii"),
            width=16,
            height=16,
            byte_size=len(payload),
        )

    def test_screenshot_success_means_verified_file_exists(self):
        capture = self._jpeg_capture()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = save_capture(capture, directory=Path(temp_dir))

            self.assertTrue(path.is_file())
            payload = path.read_bytes()
            self.assertGreater(len(payload), 64)
            self.assertTrue(payload.startswith(b"\xff\xd8\xff"))
            self.assertTrue(payload.endswith(b"\xff\xd9"))
            self.assertEqual(list(Path(temp_dir).glob("*.tmp")), [])

    def test_invalid_jpeg_is_rejected_without_creating_false_success_file(self):
        broken = b"not-a-jpeg" * 20
        capture = CapturedScreen(
            data_url=JPEG_PREFIX + base64.b64encode(broken).decode("ascii"),
            width=16,
            height=16,
            byte_size=len(broken),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ScreenshotError):
                save_capture(capture, directory=Path(temp_dir))
            self.assertEqual(list(Path(temp_dir).iterdir()), [])


class ScreenRecordingReleaseTests(unittest.TestCase):
    def test_recording_command_never_claims_verified_recording_state(self):
        module = SystemScreenRecordingModule()
        with patch("app.modules.system.screen_recording_module.send_hotkey") as hotkey:
            start = module.handle("начни запись экрана")
            stop = module.handle("останови запись экрана")
            semantic = module.execute_action("screen_recording.toggle", {})

        self.assertEqual(hotkey.call_count, 3)
        for response in (start, stop, semantic):
            self.assertIsNotNone(response)
            text = response.text.lower()
            self.assertIn("windows", text)
            self.assertNotIn("запись началась", text)
            self.assertNotIn("запись остановлена", text)
            self.assertNotIn("запись сохранена", text)


if __name__ == "__main__":
    unittest.main()
