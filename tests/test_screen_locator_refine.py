import base64
import io
import unittest

from PIL import Image

from app.api.neuro_client import (
    MIN_SCREEN_ANNOTATION_CONFIDENCE,
    _build_enlarged_screen_crop,
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
            "label": "Ассистент",
            "kind": "target",
            "x": 0.62,
            "y": 0.12,
            "width": 0.09,
            "height": 0.05,
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
    def test_uncertain_target_requests_one_enlarged_crop(self) -> None:
        self.assertTrue(_needs_enlarged_crop(screen_data(0.77)))
        self.assertFalse(
            _needs_enlarged_crop(
                screen_data(MIN_SCREEN_ANNOTATION_CONFIDENCE),
            ),
        )

    def test_missing_confidence_keeps_legacy_response_compatible(self) -> None:
        data = screen_data(0.5)
        data["annotations"][0].pop("confidence")

        self.assertFalse(_needs_enlarged_crop(data))

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

    def test_crop_is_a_valid_jpeg_and_contains_candidate(self) -> None:
        result = _build_enlarged_screen_crop(
            jpeg_data_url(),
            screen_data(0.4)["annotations"][0],
        )

        self.assertIsNotNone(result)
        crop_data_url, transform = result
        self.assertTrue(crop_data_url.startswith("data:image/jpeg;base64,"))
        self.assertLessEqual(transform.left, 0.62)
        self.assertLessEqual(transform.top, 0.12)
        self.assertGreaterEqual(transform.left + transform.width, 0.71)
        self.assertGreaterEqual(transform.top + transform.height, 0.17)

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


if __name__ == "__main__":
    unittest.main()
