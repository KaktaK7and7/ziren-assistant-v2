import base64
import hashlib
import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from app.drawings.store import DrawingStore


def make_png_data_url() -> tuple[str, str]:
    buffer = io.BytesIO()
    Image.new("RGB", (32, 24), color=(245, 241, 228)).save(
        buffer,
        format="PNG",
    )
    image_bytes = buffer.getvalue()
    return (
        "data:image/png;base64,"
        + base64.b64encode(image_bytes).decode("ascii"),
        hashlib.sha256(image_bytes).hexdigest(),
    )


class DrawingStoreTests(unittest.TestCase):
    def test_saves_lists_and_reads_a_local_drawing(self) -> None:
        image_data_url, checksum = make_png_data_url()

        with tempfile.TemporaryDirectory() as temporary_directory:
            store = DrawingStore(
                user_id=17,
                app_dir=Path(temporary_directory),
            )
            saved = store.save(
                {
                    "kind": "technical",
                    "title": "Робо-рука",
                    "prompt": "Суставы и привод манипулятора",
                    "story_relevant": False,
                    "completion_line": "Ну? Что скажешь?",
                },
                {
                    "image_data_url": image_data_url,
                    "model": "gpt-image-test",
                    "sha256": checksum,
                },
            )

            self.assertEqual(saved["title"], "Робо-рука")
            self.assertNotIn("image_data_url", saved)
            self.assertTrue(
                saved["thumbnail_data_url"].startswith(
                    "data:image/jpeg;base64,",
                ),
            )

            listed = store.list()
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["id"], saved["id"])

            full = store.get(saved["id"])
            self.assertEqual(full["image_data_url"], image_data_url)
            self.assertEqual(full["sha256"], checksum)

    def test_keeps_accounts_in_separate_local_namespaces(self) -> None:
        image_data_url, checksum = make_png_data_url()

        with tempfile.TemporaryDirectory() as temporary_directory:
            app_dir = Path(temporary_directory)
            first_store = DrawingStore(user_id=1, app_dir=app_dir)
            second_store = DrawingStore(user_id=2, app_dir=app_dir)
            first_store.save(
                {
                    "kind": "story",
                    "title": "Сигнал",
                    "prompt": "Фрагмент коридора",
                },
                {
                    "image_data_url": image_data_url,
                    "sha256": checksum,
                },
            )

            self.assertEqual(len(first_store.list()), 1)
            self.assertEqual(second_store.list(), [])
            self.assertNotEqual(first_store.root, second_store.root)

    def test_rejects_invalid_image_or_checksum(self) -> None:
        image_data_url, _ = make_png_data_url()

        with tempfile.TemporaryDirectory() as temporary_directory:
            store = DrawingStore(
                user_id=1,
                app_dir=Path(temporary_directory),
            )
            request = {
                "kind": "sketch",
                "title": "Тест",
                "prompt": "Тестовый рисунок",
            }

            with self.assertRaises(ValueError):
                store.save(
                    request,
                    {
                        "image_data_url": "data:image/png;base64,bad",
                    },
                )

            with self.assertRaises(ValueError):
                store.save(
                    request,
                    {
                        "image_data_url": image_data_url,
                        "sha256": "0" * 64,
                    },
                )

    def test_keeps_local_screen_analyses_as_a_separate_kind(self) -> None:
        image_data_url, checksum = make_png_data_url()

        with tempfile.TemporaryDirectory() as temporary_directory:
            store = DrawingStore(
                user_id=1,
                app_dir=Path(temporary_directory),
            )
            saved = store.save(
                {
                    "kind": "screen",
                    "title": "Разбор экрана",
                    "prompt": "1. Кнопка Продолжить",
                },
                {
                    "image_data_url": image_data_url,
                    "sha256": checksum,
                    "model": "ziren-local-screen-annotation",
                },
            )

            self.assertEqual(saved["kind"], "screen")

if __name__ == "__main__":
    unittest.main()
