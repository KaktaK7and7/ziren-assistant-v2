import base64
import io
import unittest

from PIL import Image

from app.vision.screen_capture import (
    CapturedScreen,
    build_grounded_screen_data_url,
    is_screen_analysis_request,
    is_screen_canvas_request,
    is_screen_click_request,
)


class ScreenCaptureIntentTests(unittest.TestCase):
    def test_explicit_screen_questions_enable_visual_context(self) -> None:
        for text in (
            "что у меня на экране",
            "посмотри на экран и помоги разобраться что тут делать",
            "объясни, что нажать в этом окне",
            "переведи текст на экране",
            "сохрани разбор экрана в холст",
        ):
            with self.subTest(text=text):
                self.assertTrue(is_screen_analysis_request(text))

    def test_unrelated_help_does_not_capture_screen(self) -> None:
        for text in (
            "помоги мне разобраться",
            "что мне делать дальше",
            "расскажи про новый монитор",
        ):
            with self.subTest(text=text):
                self.assertFalse(is_screen_analysis_request(text))

    def test_direct_click_targets_and_recent_click_followups_use_screen(self) -> None:
        self.assertTrue(
            is_screen_analysis_request("нажми на мой профиль"),
        )
        self.assertTrue(
            is_screen_analysis_request("кликни кнопку ассистент"),
        )
        self.assertFalse(is_screen_analysis_request("ну давай нажимай"))
        self.assertTrue(
            is_screen_analysis_request(
                "ну давай нажимай",
                allow_click_followup=True,
            ),
        )

    def test_click_and_canvas_require_explicit_words(self) -> None:
        self.assertTrue(
            is_screen_click_request("нажми продолжить на экране"),
        )
        self.assertFalse(
            is_screen_click_request("покажи, где кнопка продолжить"),
        )
        self.assertTrue(
            is_screen_canvas_request("сохрани разбор экрана в холст"),
        )
        self.assertFalse(
            is_screen_canvas_request("объясни, что на экране"),
        )

    def test_grounding_grid_keeps_dimensions_and_original_capture(self) -> None:
        image = Image.new("RGB", (320, 180), (20, 30, 40))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=80)
        original_url = (
            "data:image/jpeg;base64,"
            + base64.b64encode(buffer.getvalue()).decode("ascii")
        )
        capture = CapturedScreen(
            data_url=original_url,
            width=320,
            height=180,
            byte_size=len(buffer.getvalue()),
            foreground_window=17,
        )

        grounded_url = build_grounded_screen_data_url(capture)

        self.assertEqual(capture.data_url, original_url)
        self.assertNotEqual(grounded_url, original_url)
        grounded = Image.open(
            io.BytesIO(base64.b64decode(grounded_url.split(",", 1)[1])),
        )
        self.assertEqual(grounded.size, (320, 180))


if __name__ == "__main__":
    unittest.main()
