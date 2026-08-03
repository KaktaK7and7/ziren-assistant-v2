import base64
import io
import unittest

from PIL import Image

from app.vision.annotated_capture import render_annotated_capture


class AnnotatedCaptureTests(unittest.TestCase):
    def test_renders_screen_plan_as_a_local_canvas_png(self) -> None:
        source = io.BytesIO()
        Image.new("RGB", (320, 180), color=(24, 28, 34)).save(
            source,
            format="JPEG",
        )
        request, generated = render_annotated_capture(
            "data:image/jpeg;base64,"
            + base64.b64encode(source.getvalue()).decode("ascii"),
            {
                "mode": "guide",
                "answer": "Нажми кнопку.",
                "annotations": [{
                    "id": "next",
                    "label": "Продолжить",
                    "kind": "target",
                    "x": 0.6,
                    "y": 0.6,
                    "width": 0.25,
                    "height": 0.18,
                    "step": 1,
                }],
            },
        )

        self.assertEqual(request["kind"], "screen")
        self.assertIn("Нажми кнопку", request["prompt"])
        self.assertIn("Продолжить", request["prompt"])
        self.assertTrue(
            generated["image_data_url"].startswith(
                "data:image/png;base64,",
            ),
        )
        self.assertEqual(len(generated["sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
