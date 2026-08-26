from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from app.config.release_paths import (
    VOSK_MODEL_ENV,
    get_vosk_model_path,
    validate_vosk_model_path,
)
from scripts import prepare_windows_release_assets as release_assets


class ReleasePathTests(unittest.TestCase):
    def test_vosk_path_can_be_overridden_for_packaged_build(self):
        with tempfile.TemporaryDirectory() as temporary:
            expected = Path(temporary).resolve()
            with patch.dict(os.environ, {VOSK_MODEL_ENV: str(expected)}):
                self.assertEqual(get_vosk_model_path(), expected)

    def test_incomplete_vosk_model_is_rejected_before_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            model = Path(temporary)
            (model / "am").mkdir()
            with self.assertRaisesRegex(FileNotFoundError, "incomplete"):
                validate_vosk_model_path(model)

    def test_complete_model_markers_are_accepted(self):
        with tempfile.TemporaryDirectory() as temporary:
            model = Path(temporary)
            for marker in ("am", "conf", "graph"):
                (model / marker).mkdir()
            self.assertEqual(validate_vosk_model_path(model), model.resolve())


class ReleaseAssetTests(unittest.TestCase):
    def test_archive_hash_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "model.zip"
            archive.write_bytes(b"not the expected model")
            with self.assertRaisesRegex(release_assets.ReleaseAssetError, "SHA-256"):
                release_assets.verify_archive(archive)

    def test_archive_hash_can_be_verified_deterministically(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "model.zip"
            archive.write_bytes(b"deterministic release fixture")
            expected = hashlib.sha256(archive.read_bytes()).hexdigest()
            with patch.object(release_assets, "VOSK_MODEL_SHA256", expected):
                release_assets.verify_archive(archive)

    def test_zip_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "unsafe.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("../escape.txt", "nope")

            destination = root / "extract"
            with self.assertRaisesRegex(release_assets.ReleaseAssetError, "Unsafe ZIP entry"):
                release_assets.safe_extract_zip(archive, destination)
            self.assertFalse((root / "escape.txt").exists())

    def test_safe_model_archive_extracts_inside_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "safe.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr(
                    f"{release_assets.VOSK_MODEL_NAME}/conf/model.conf",
                    "fixture",
                )

            destination = root / "extract"
            release_assets.safe_extract_zip(archive, destination)
            self.assertEqual(
                (destination / release_assets.VOSK_MODEL_NAME / "conf" / "model.conf").read_text(),
                "fixture",
            )


if __name__ == "__main__":
    unittest.main()
