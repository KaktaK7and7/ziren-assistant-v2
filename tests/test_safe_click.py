import unittest

from app.vision.safe_click import normalized_to_pixels, point_inside_rect


class SafeClickTests(unittest.TestCase):
    def test_maps_normalized_coordinates_inside_primary_screen(self) -> None:
        self.assertEqual(
            normalized_to_pixels(0.5, 0.5, 1920, 1080),
            (960, 540),
        )
        self.assertEqual(
            normalized_to_pixels(1, 1, 1920, 1080),
            (1919, 1079),
        )

    def test_rejects_coordinates_outside_the_screen(self) -> None:
        with self.assertRaises(ValueError):
            normalized_to_pixels(1.1, 0.5, 1920, 1080)

    def test_target_must_stay_inside_the_analyzed_window(self) -> None:
        self.assertTrue(point_inside_rect(400, 300, 100, 100, 900, 700))
        self.assertFalse(point_inside_rect(80, 300, 100, 100, 900, 700))


if __name__ == "__main__":
    unittest.main()
