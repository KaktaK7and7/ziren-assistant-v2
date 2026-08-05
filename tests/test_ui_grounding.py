import unittest

from app.vision.screen_capture import CapturedScreen
from app.vision.ui_grounding import (
    MAX_UI_ELEMENTS,
    MAX_UI_TREE_DEPTH,
    MIN_GROUNDING_CONFIDENCE,
    UiElement,
    UiElementBatch,
    _UiCollectionRequest,
    _collect_ui_elements_on_automation_thread,
    ground_screen_annotations,
)


def make_annotation(
    label: str = "Кнопка профиля 'Как_так?'",
) -> dict:
    return {
        "id": "profile",
        "label": label,
        "kind": "target",
        "x": 0.82,
        "y": 0.04,
        "width": 0.1,
        "height": 0.07,
        "step": 1,
    }


class UiGroundingTests(unittest.TestCase):
    def test_browser_walk_uses_deep_limits(self) -> None:
        self.assertEqual(MAX_UI_ELEMENTS, 5000)
        self.assertEqual(MAX_UI_TREE_DEPTH, 32)
        self.assertEqual(MIN_GROUNDING_CONFIDENCE, 0.78)

    def test_windows_physical_bounds_use_original_screen_dimensions(self) -> None:
        class Rect:
            left = 1460
            top = 122
            right = 1565
            bottom = 168

        class Control:
            Name = "Как_так?"
            IsOffscreen = False
            BoundingRectangle = Rect()
            ControlTypeName = "ButtonControl"
            AutomationId = "profile"
            ClassName = "button"

            @staticmethod
            def GetChildren() -> list:
                return []

        class Automation:
            @staticmethod
            def ControlFromHandle(_handle: int) -> Control:
                return Control()

        capture = CapturedScreen(
            data_url="data:image/jpeg;base64,test",
            width=1600,
            height=900,
            byte_size=4,
            foreground_window=17,
            source_width=1920,
            source_height=1080,
        )

        elements = _collect_ui_elements_on_automation_thread(
            capture,
            Automation(),
        )

        self.assertEqual(len(elements), 1)
        self.assertAlmostEqual(elements[0].x, 1460 / 1920)
        self.assertAlmostEqual(elements[0].y, 122 / 1080)
        self.assertAlmostEqual(elements[0].width, 105 / 1920)

    def test_pending_batch_is_truthy_without_blocking_vision(self) -> None:
        capture = CapturedScreen(
            data_url="data:image/jpeg;base64,test",
            width=1600,
            height=900,
            byte_size=4,
            foreground_window=17,
        )
        request = _UiCollectionRequest(capture=capture)
        batch = UiElementBatch(request)

        self.assertTrue(batch)
        self.assertEqual(len(batch), 0)

        request.elements = [UiElement(
            name="Ассистент",
            control_type="HyperlinkControl",
            x=0.2,
            y=0.2,
            width=0.1,
            height=0.05,
        )]
        request.done.set()

        self.assertEqual(len(list(batch)), 1)
        self.assertEqual(len(batch), 1)

    def test_exact_accessible_name_replaces_model_coordinates(self) -> None:
        annotations, verified, matches = ground_screen_annotations(
            [make_annotation()],
            {
                "type": "click",
                "target_id": "profile",
                "label": "Нажать кнопку профиля 'Как_так?'",
            },
            [UiElement(
                name="Как_так?",
                control_type="ButtonControl",
                x=0.76,
                y=0.115,
                width=0.055,
                height=0.043,
            )],
        )

        self.assertEqual(verified, {"profile"})
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].element_name, "Как_так?")
        self.assertGreaterEqual(
            matches[0].confidence,
            MIN_GROUNDING_CONFIDENCE,
        )
        self.assertAlmostEqual(annotations[0]["x"], 0.76)
        self.assertAlmostEqual(annotations[0]["y"], 0.115)
        self.assertAlmostEqual(annotations[0]["width"], 0.055)

    def test_interactive_element_wins_over_duplicate_text(self) -> None:
        annotations, verified, matches = ground_screen_annotations(
            [make_annotation("Кнопка 'Ассистент'")],
            {
                "type": "click",
                "target_id": "profile",
                "label": "Нажать вкладку Ассистент",
            },
            [
                UiElement(
                    name="Ассистент",
                    control_type="TextControl",
                    x=0.61,
                    y=0.12,
                    width=0.06,
                    height=0.03,
                ),
                UiElement(
                    name="Ассистент",
                    control_type="HyperlinkControl",
                    x=0.60,
                    y=0.11,
                    width=0.075,
                    height=0.045,
                ),
            ],
        )

        self.assertEqual(verified, {"profile"})
        self.assertEqual(matches[0].control_type, "HyperlinkControl")
        self.assertAlmostEqual(annotations[0]["x"], 0.60)

    def test_unrelated_element_hides_approximate_target(self) -> None:
        annotations, verified, matches = ground_screen_annotations(
            [make_annotation()],
            {
                "type": "click",
                "target_id": "profile",
                "label": "Нажать профиль",
            },
            [UiElement(
                name="Сообщество",
                control_type="HyperlinkControl",
                x=0.55,
                y=0.12,
                width=0.07,
                height=0.04,
            )],
        )

        self.assertEqual(verified, set())
        self.assertEqual(matches, [])
        self.assertEqual(annotations, [])

    def test_weak_partial_match_below_threshold_is_hidden(self) -> None:
        annotations, verified, matches = ground_screen_annotations(
            [make_annotation("Профиль пользователя")],
            {},
            [UiElement(
                name="Профили разработчиков и новости",
                control_type="TextControl",
                x=0.2,
                y=0.2,
                width=0.3,
                height=0.08,
            )],
        )

        self.assertEqual(annotations, [])
        self.assertEqual(verified, set())
        self.assertEqual(matches, [])

    def test_non_target_annotations_are_not_repositioned(self) -> None:
        annotation = make_annotation("Важный текст")
        annotation["kind"] = "text"
        annotations, verified, matches = ground_screen_annotations(
            [annotation],
            {},
            [UiElement(
                name="Важный текст",
                control_type="TextControl",
                x=0.1,
                y=0.1,
                width=0.2,
                height=0.1,
            )],
        )

        self.assertEqual(verified, set())
        self.assertEqual(matches, [])
        self.assertEqual(annotations[0]["x"], annotation["x"])


if __name__ == "__main__":
    unittest.main()
