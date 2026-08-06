import base64
import io
import unittest

from PIL import Image

from app.api.neuro_client import (
    MIN_SCREEN_ANNOTATION_CONFIDENCE,
    _build_enlarged_screen_crop,
    _mark_unverified_targets,
    _merge_refined_annotation,
    _needs_enlarged_crop,
    _remap_crop_annotations,
    _select_retry_annotation,
)


def jpeg_data_url(width: int = 1000, height: int = 700) -> str:
    image = Image.new("RGB", (width, height), (20, 30, 40))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    return (
        "data:image/jpeg;base64,"
        + base64.b64encode(buffer.getvalue()).decode("ascii")
    )


def screen_data(confidence: float) -> dict:
    return {
        "annotations": [{
            "id": "assistant-tab",
            "label": "Кнопка Ассистент",
            "kind": "target",
            "x": 0.80,
            "y": 0.05,
            "width": 0.10,
            "height": 0.06,
            "step": 0,
            "confidence": confidence,
        }],
        "action": {
            "type": "click",
            "target_id": "assistant-tab",
            "label": "Ассистент",
            "risk": "safe",
            "reason": "",
        },
    }


class ScreenLocatorRefineTests(unittest.TestCase):
    def test_every_target_requests_zoomed_verification(self) -> None:
        self.assertTrue(_needs_enlarged_crop(screen_data(0.25)))
        self.assertTrue(_needs_enlarged_crop(screen_data(0.99)))
        data = screen_data(0.9)
        data["annotations"][0].pop("confidence")
        self.assertTrue(_needs_enlarged_crop(data))

    def test_action_target_is_selected_before_other_annotations(self) -> None:
        data = screen_data(0.6)
        data["annotations"].insert(0, {
            "id": "other",
            "label": "Сообщество",
            "kind": "target",
            "x": 0.2,
            "y": 0.2,
            "width": 0.1,
            "height": 0.05,
            "confidence": 0.95,
        })
        selected = _select_retry_annotation(data)
        self.assertIsNotNone(selected)
        self.assertEqual(selected["id"], "assistant-tab")

    def test_first_pass_target_is_disabled_as_visual_fallback(self) -> None:
        marked = _mark_unverified_targets(screen_data(0.99))
        annotation = marked["annotations"][0]
        self.assertEqual(annotation["confidence"], 0.0)
        self.assertNotIn("_visual_refined", annotation)

    def test_crop_covers_smoke_test_coordinate_error(self) -> None:
        result = _build_enlarged_screen_crop(
            jpeg_data_url(),
            screen_data(0.99)["annotations"][0],
        )
        self.assertIsNotNone(result)
        crop_data_url, transform = result
        self.assertTrue(crop_data_url.startswith("data:image/jpeg;base64,"))
        self.assertLessEqual(transform.left, 0.63)
        self.assertLessEqual(transform.top, 0.14)
        self.assertGreaterEqual(transform.left + transform.width, 0.90)
        self.assertGreaterEqual(transform.top + transform.height, 0.20)
        raw = base64.b64decode(crop_data_url.split(",", 1)[1])
        image = Image.open(io.BytesIO(raw))
        self.assertEqual(image.format, "JPEG")

    def test_crop_coordinates_are_remapped_to_full_screen(self) -> None:
        data = {
            "annotations": [{
                "id": "assistant-tab",
                "label": "Ассистент",
                "kind": "target",
                "x": 0.25,
                "y": 0.5,
                "width": 0.2,
                "height": 0.1,
                "confidence": 0.91,
            }],
        }
        original = screen_data(0.4)["annotations"][0]
        crop_result = _build_enlarged_screen_crop(jpeg_data_url(), original)
        self.assertIsNotNone(crop_result)
        _, transform = crop_result
        remapped = _remap_crop_annotations(data, transform)
        annotation = remapped["annotations"][0]
        self.assertAlmostEqual(
            annotation["x"],
            transform.left + 0.25 * transform.width,
        )
        self.assertAlmostEqual(
            annotation["y"],
            transform.top + 0.5 * transform.height,
        )
        self.assertAlmostEqual(
            annotation["width"],
            0.2 * transform.width,
        )

    def test_matching_zoomed_result_becomes_visual_only_verified(self) -> None:
        original = screen_data(0.99)["annotations"][0]
        refined = {
            "id": "different-service-id",
            "label": "Ассистент",
            "kind": "target",
            "x": 0.625,
            "y": 0.115,
            "width": 0.065,
            "height": 0.035,
            "step": 0,
            "confidence": 0.88,
        }
        merged = _merge_refined_annotation(original, refined)
        self.assertIsNotNone(merged)
        self.assertEqual(merged["id"], "assistant-tab")
        self.assertEqual(merged["label"], "Кнопка Ассистент")
        self.assertAlmostEqual(merged["x"], 0.625)
        self.assertTrue(merged["_visual_refined"])
        self.assertGreaterEqual(
            merged["confidence"],
            MIN_SCREEN_ANNOTATION_CONFIDENCE,
        )

    def test_unrelated_or_uncertain_zoomed_result_is_rejected(self) -> None:
        original = screen_data(0.99)["annotations"][0]
        unrelated = dict(original)
        unrelated.update({
            "label": "Сообщество",
            "x": 0.5,
            "confidence": 0.95,
        })
        self.assertIsNone(_merge_refined_annotation(original, unrelated))
        uncertain = dict(original)
        uncertain.update({
            "label": "Ассистент",
            "x": 0.63,
            "confidence": MIN_SCREEN_ANNOTATION_CONFIDENCE - 0.01,
        })
        self.assertIsNone(_merge_refined_annotation(original, uncertain))


if __name__ == "__main__":
    unittest.main()
