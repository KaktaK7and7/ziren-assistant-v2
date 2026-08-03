import unittest

from app.vision.analysis_store import ScreenAnalysisStore
from app.vision.screen_capture import CapturedScreen


def make_capture() -> CapturedScreen:
    return CapturedScreen(
        data_url="data:image/jpeg;base64,/9j/test",
        width=1200,
        height=800,
        byte_size=8,
        foreground_window=713,
    )


def make_plan(label: str = "Продолжить") -> dict:
    return {
        "answer": "Нужная кнопка справа.",
        "mode": "guide",
        "annotations": [{
            "id": "next",
            "label": label,
            "kind": "target",
            "x": 0.7,
            "y": 0.75,
            "width": 0.2,
            "height": 0.1,
            "step": 1,
        }],
        "action": {
            "type": "click",
            "target_id": "next",
            "label": label,
            "risk": "safe",
            "reason": "Обратимый переход.",
        },
    }


class ScreenAnalysisStoreTests(unittest.TestCase):
    def test_click_requires_explicit_request_and_is_single_use(self) -> None:
        store = ScreenAnalysisStore()
        passive = store.create(
            make_capture(),
            make_plan(),
            click_was_requested=False,
        )
        self.assertFalse(passive["action"]["available"])
        self.assertFalse(passive["action"]["requested"])

        active = store.create(
            make_capture(),
            make_plan(),
            click_was_requested=True,
        )
        self.assertTrue(active["action"]["available"])
        self.assertTrue(active["action"]["requested"])
        click = store.take_confirmed_click(active["id"])
        self.assertAlmostEqual(click["x"], 0.8)
        self.assertAlmostEqual(click["y"], 0.8)
        self.assertEqual(click["foreground_window"], 713)

        with self.assertRaises(KeyError):
            store.take_confirmed_click(active["id"])

    def test_risky_action_is_blocked_even_if_model_marks_it_safe(self) -> None:
        result = ScreenAnalysisStore().create(
            make_capture(),
            make_plan("Удаляем аккаунт"),
            click_was_requested=True,
        )
        self.assertFalse(result["action"]["available"])
        self.assertEqual(result["action"]["risk"], "blocked")

    def test_screenshot_is_not_exposed_in_public_payload(self) -> None:
        store = ScreenAnalysisStore()
        result = store.create(
            make_capture(),
            make_plan(),
            click_was_requested=False,
        )
        self.assertNotIn("image_data_url", result)
        source = store.get_canvas_source(result["id"])
        self.assertIn("image_data_url", source)

        store.mark_canvas_saved(result["id"], "drawing-17")
        saved_source = store.get_canvas_source(result["id"])
        self.assertEqual(saved_source["drawing_id"], "drawing-17")
        self.assertNotIn("image_data_url", saved_source)


if __name__ == "__main__":
    unittest.main()
