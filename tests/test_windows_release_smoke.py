import json
import tempfile
import unittest
from pathlib import Path

from scripts.windows_release_smoke import (
    SMOKE_CASES,
    SmokeResult,
    build_report,
    selected_cases,
    write_report,
)


class WindowsReleaseSmokeTests(unittest.TestCase):
    def test_session_ending_cases_are_hidden_by_default(self):
        cases = selected_cases(include_session_ending=False, monitor_count=2)

        self.assertTrue(cases)
        self.assertTrue(all(not case.session_ending for case in cases))
        self.assertNotIn("power.sleep", {case.case_id for case in cases})
        self.assertNotIn("power.restart", {case.case_id for case in cases})

    def test_session_ending_cases_require_explicit_opt_in(self):
        cases = selected_cases(include_session_ending=True, monitor_count=2)
        case_ids = {case.case_id for case in cases}

        self.assertIn("power.lock", case_ids)
        self.assertIn("power.sleep", case_ids)
        self.assertIn("power.restart", case_ids)

    def test_multi_monitor_case_is_skipped_when_machine_reports_one_monitor(self):
        one_monitor = selected_cases(include_session_ending=False, monitor_count=1)
        unknown_monitor_count = selected_cases(
            include_session_ending=False,
            monitor_count=None,
        )

        self.assertNotIn(
            "display.multi_monitor",
            {case.case_id for case in one_monitor},
        )
        self.assertIn(
            "display.multi_monitor",
            {case.case_id for case in unknown_monitor_count},
        )

    def test_report_counts_pass_fail_and_skip(self):
        report = build_report(
            {"is_windows": True, "git_head": "abc123"},
            [
                SmokeResult("a", "pass"),
                SmokeResult("b", "fail", "wrong window"),
                SmokeResult("c", "skip"),
            ],
            include_session_ending=False,
        )

        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["counts"], {"skip": 1, "fail": 1, "pass": 1})
        self.assertEqual(report["diagnostics"]["git_head"], "abc123")
        self.assertFalse(report["include_session_ending"])

    def test_report_is_written_as_utf8_json(self):
        report = build_report(
            {"is_windows": True},
            [SmokeResult("keyboard.unicode.notepad", "pass", "Привет ✓")],
            include_session_ending=False,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "smoke.json"
            write_report(report, output)
            loaded = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(loaded["results"][0]["note"], "Привет ✓")

    def test_catalog_contains_required_p0_manual_gates(self):
        case_ids = {case.case_id for case in SMOKE_CASES}
        required = {
            "keyboard.unicode.notepad",
            "keyboard.unicode.chromium",
            "windows.common_apps",
            "desktops.sequence",
            "capture.screenshot",
            "recording.gamebar",
            "audio.volume",
            "scheduler.reminder_restart",
            "scheduler.alarm_restart",
            "display.brightness",
            "display.multi_monitor",
            "files.known_folders",
            "power.lock",
            "power.sleep",
            "power.restart",
        }

        self.assertTrue(required.issubset(case_ids))


if __name__ == "__main__":
    unittest.main()
