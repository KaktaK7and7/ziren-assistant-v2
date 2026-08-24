import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from app.pc_control import file_navigation
from app.pc_control.file_navigation import FileNavigationError


class FileNavigationReleaseTests(unittest.TestCase):
    def test_windows_known_folder_api_wins_over_naive_userprofile_path(self):
        fallback = {
            key: Path("C:/Users/test") / key
            for key in file_navigation.KNOWN_FOLDER_IDS
        }
        redirected = {
            guid: Path("D:/Redirected") / folder_id
            for folder_id, guid in file_navigation.KNOWN_FOLDER_IDS.items()
        }

        with (
            patch.object(file_navigation.os, "name", "nt"),
            patch("app.pc_control.file_navigation._fallback_known_folders", return_value=fallback),
            patch(
                "app.pc_control.file_navigation._known_folder_path",
                side_effect=lambda guid: redirected[guid],
            ),
        ):
            folders = file_navigation.known_folders()

        self.assertEqual(folders["desktop"], Path("D:/Redirected/desktop"))
        self.assertEqual(folders["documents"], Path("D:/Redirected/documents"))
        self.assertNotEqual(folders["desktop"], fallback["desktop"])

    def test_known_folder_failure_falls_back_only_for_that_folder(self):
        fallback = {
            key: Path("C:/Users/test") / key
            for key in file_navigation.KNOWN_FOLDER_IDS
        }
        downloads_guid = file_navigation.KNOWN_FOLDER_IDS["downloads"]

        def resolve(guid: str) -> Path:
            if guid == downloads_guid:
                raise FileNavigationError("lookup failed")
            return Path("E:/Known") / guid[-4:]

        with (
            patch.object(file_navigation.os, "name", "nt"),
            patch("app.pc_control.file_navigation._fallback_known_folders", return_value=fallback),
            patch("app.pc_control.file_navigation._known_folder_path", side_effect=resolve),
        ):
            folders = file_navigation.known_folders()

        self.assertEqual(folders["downloads"], fallback["downloads"])
        self.assertNotEqual(folders["documents"], fallback["documents"])

    def test_latest_download_ignores_partial_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            completed = root / "report.pdf"
            partial = root / "newer.crdownload"
            completed.write_text("ok", encoding="utf-8")
            partial.write_text("partial", encoding="utf-8")
            now = time.time()
            os.utime(completed, (now - 10, now - 10))
            os.utime(partial, (now, now))

            with patch(
                "app.pc_control.file_navigation.resolve_known_folder",
                return_value=root,
            ):
                latest = file_navigation.latest_download()

        self.assertEqual(latest.name, "report.pdf")

    def test_download_voice_open_is_allowlist_only(self):
        for unsafe in (
            "installer.exe",
            "setup.msi",
            "script.bat",
            "script.cmd",
            "script.ps1",
            "script.py",
            "payload.jar",
            "shortcut.lnk",
        ):
            with self.subTest(unsafe=unsafe):
                self.assertFalse(file_navigation.is_safe_to_open(Path(unsafe)))

        for safe in ("manual.pdf", "photo.jpg", "video.mp4", "model.blend"):
            with self.subTest(safe=safe):
                self.assertTrue(file_navigation.is_safe_to_open(Path(safe)))


if __name__ == "__main__":
    unittest.main()
