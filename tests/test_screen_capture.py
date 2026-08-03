import unittest

from app.vision.screen_capture import (
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


if __name__ == "__main__":
    unittest.main()
