import unittest

from app.vision.screen_capture import is_screen_analysis_request


class ScreenCaptureIntentTests(unittest.TestCase):
    def test_explicit_screen_questions_enable_visual_context(self) -> None:
        for text in (
            "что у меня на экране",
            "посмотри на экран и помоги разобраться что тут делать",
            "объясни, что нажать в этом окне",
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


if __name__ == "__main__":
    unittest.main()
