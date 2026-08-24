from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


REPORT_SCHEMA_VERSION = 1
DEFAULT_REPORT_DIR = Path("build") / "release-smoke"
VALID_RESULTS = {"pass", "fail", "skip"}


@dataclass(frozen=True)
class SmokeCase:
    case_id: str
    area: str
    title: str
    instructions: tuple[str, ...]
    session_ending: bool = False
    requires_two_monitors: bool = False


@dataclass
class SmokeResult:
    case_id: str
    result: str
    note: str = ""


SMOKE_CASES: tuple[SmokeCase, ...] = (
    SmokeCase(
        "keyboard.unicode.notepad",
        "Keyboard",
        "Unicode input in Notepad",
        (
            "Open Notepad and focus an empty document.",
            "Ask Ziren to type: Привет, Ziren — ёжик №7 ✓",
            "PASS only if the exact Unicode text appears without missing or duplicated characters.",
        ),
    ),
    SmokeCase(
        "keyboard.unicode.chromium",
        "Keyboard",
        "Unicode input in a Chromium text field",
        (
            "Open a Chromium-based browser and focus a normal text field.",
            "Ask Ziren to type the same Unicode sample used in Notepad.",
            "PASS only if the field contains the exact text.",
        ),
    ),
    SmokeCase(
        "keyboard.unicode.win32",
        "Keyboard",
        "Unicode input in a standard Win32 edit control",
        (
            "Open a normal Windows application that uses a standard editable text control.",
            "Focus the edit control and ask Ziren to type: Привет, Ziren — ёжик №7 ✓",
            "PASS only if the exact Unicode text appears and focus stays in the intended field.",
        ),
    ),
    SmokeCase(
        "keyboard.function_keys",
        "Keyboard",
        "F1–F12 voice addressability",
        (
            "Use a harmless application where function-key input can be observed without risking data loss.",
            "Run the Snake F1–F12 voice commands and verify each requested function key is the one delivered.",
            "Also test one Melissa natural-language F-key request and verify it is bounded to F1–F12.",
        ),
    ),
    SmokeCase(
        "keyboard.hotkeys",
        "Keyboard",
        "Curated Ctrl / Alt / Win hotkeys",
        (
            "Use disposable text and normal application windows.",
            "Verify representative Ctrl shortcuts (select/copy/paste/undo), Alt+Tab, Win+D and task view.",
            "PASS only if no modifier remains stuck and rapid commands do not lose the intended Shell action.",
        ),
    ),
    SmokeCase(
        "clipboard.text",
        "Clipboard",
        "Clipboard write / read / paste path",
        (
            "Ask Ziren to put a distinctive Unicode phrase into the clipboard.",
            "Ask Ziren to read it back, then paste it into Notepad.",
            "PASS only if the exact clipboard value survives write, read-back and paste; social send must not steal the local clipboard command.",
        ),
    ),
    SmokeCase(
        "windows.common_apps",
        "Windows",
        "Focus / minimize / maximize / restore common windows",
        (
            "Open Explorer, Notepad and a Chromium browser at the same time.",
            "Test focus, minimize, maximize and restore against each app by spoken name.",
            "FAIL on wrong-window selection, false success or ambiguous selection that performs an action.",
        ),
    ),
    SmokeCase(
        "windows.close",
        "Windows",
        "Graceful WM_CLOSE against normal applications",
        (
            "Open disposable Explorer and Notepad windows with no unsaved important work.",
            "Ask Ziren to close each window by name.",
            "PASS only if the normal application close path is used, ambiguity performs no action, and Ziren never force-kills the process.",
        ),
    ),
    SmokeCase(
        "desktops.sequence",
        "Virtual desktops",
        "Deterministic 1 → 2 → 1 → 3 → 1 sequence",
        (
            "Create at least three virtual desktops and leave a recognisable window on each.",
            "Ask Ziren to go 1 → 2 → 1 → 3 → 1 using numbered desktop commands.",
            "PASS only if every transition lands on the expected desktop without skipped Shell hotkeys.",
        ),
    ),
    SmokeCase(
        "capture.screenshot",
        "Capture",
        "Real screenshot capture and folder open",
        (
            "Ask Ziren to take a screenshot.",
            "Confirm a valid JPEG is created in Pictures/Ziren/Screenshots.",
            "Ask Ziren to open the screenshot folder and verify the expected folder opens.",
        ),
    ),
    SmokeCase(
        "recording.gamebar",
        "Capture",
        "Windows Game Bar recording command honesty",
        (
            "With Game Bar enabled, ask Ziren to toggle screen recording.",
            "Verify Windows itself shows the recording state.",
            "PASS only if Ziren reports command delivery rather than claiming an unverified recording state.",
        ),
    ),
    SmokeCase(
        "audio.volume",
        "Audio",
        "Volume set / mute / unmute read-back",
        (
            "Set volume to a distinctive value such as 37 percent through Ziren.",
            "Verify the Windows endpoint actually reports the requested level.",
            "Test mute and unmute and verify the endpoint state changes each time.",
        ),
    ),
    SmokeCase(
        "scheduler.reminder_restart",
        "Scheduler",
        "Reminder survives Core restart",
        (
            "Create a reminder several minutes in the future.",
            "Restart only the Ziren Core/Desktop application before it is due.",
            "PASS only if the reminder is delivered once after restart and disappears after successful delivery.",
        ),
    ),
    SmokeCase(
        "scheduler.alarm_restart",
        "Scheduler",
        "Alarm survives Core restart and can be cancelled",
        (
            "Create an alarm several minutes in the future and restart Ziren before it is due.",
            "Verify audible delivery after restart.",
            "Repeat with another alarm, cancel it shortly before due time, and verify it does not beep or speak.",
        ),
    ),
    SmokeCase(
        "display.brightness",
        "Display",
        "DDC/CI brightness success and unsupported-device honesty",
        (
            "On a DDC/CI-capable display, change brightness through Ziren and verify physical read-back.",
            "If another display does not support DDC/CI, test it too.",
            "PASS only if unsupported hardware is reported as unsupported instead of false success.",
        ),
    ),
    SmokeCase(
        "display.multi_monitor",
        "Display",
        "Move active window between physical monitors",
        (
            "With at least two physical monitors, focus a normal application window.",
            "Ask Ziren to move it left and right between monitors.",
            "PASS only if Core verifies that the window's monitor handle actually changed.",
        ),
        requires_two_monitors=True,
    ),
    SmokeCase(
        "files.known_folders",
        "Files",
        "Known folders including OneDrive/redirection",
        (
            "Open Downloads, Documents, Desktop, Pictures, Videos and Music through Ziren.",
            "If OneDrive or folder redirection is enabled, verify Ziren follows the Windows Known Folder location.",
            "FAIL if Ziren silently opens a naive USERPROFILE path instead of the configured folder.",
        ),
    ),
    SmokeCase(
        "files.latest_download",
        "Files",
        "Reveal/open latest downloaded file safely",
        (
            "Place a harmless supported document in Downloads and make sure no partial .crdownload/.part file is newer.",
            "Ask Ziren to reveal the latest download, then open it.",
            "PASS only if the expected safe file is selected/opened and executable or unknown types are refused.",
        ),
    ),
    SmokeCase(
        "power.lock",
        "Power",
        "Lock workstation",
        (
            "Save any work before this test.",
            "Ask Ziren to lock the workstation.",
            "PASS only if Windows reaches the lock screen and Ziren did not require an unsafe shell command.",
        ),
        session_ending=True,
    ),
    SmokeCase(
        "power.sleep",
        "Power",
        "Sleep confirmation path",
        (
            "Save all work before this test.",
            "Request sleep and verify nothing happens before a separate confirmation.",
            "Confirm within the allowed window and verify the PC sleeps.",
        ),
        session_ending=True,
    ),
    SmokeCase(
        "power.restart",
        "Power",
        "Restart confirmation path",
        (
            "Run this near the end of the smoke batch and save all work.",
            "Request restart and verify nothing happens before a separate confirmation.",
            "Confirm within the allowed window and verify Windows restarts normally.",
        ),
        session_ending=True,
    ),
    SmokeCase(
        "power.shutdown",
        "Power",
        "Shutdown confirmation path",
        (
            "Run this last and save all work before continuing.",
            "Request shutdown and verify nothing happens before a separate confirmation.",
            "Confirm within the allowed window and verify Windows shuts down normally.",
        ),
        session_ending=True,
    ),
)


def _git_head() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _monitor_count() -> int | None:
    if os.name != "nt":
        return None
    try:
        import ctypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        return int(user32.GetSystemMetrics(80))  # SM_CMONITORS
    except Exception:
        return None


def collect_safe_diagnostics() -> dict:
    monitor_count = _monitor_count()
    return {
        "os_name": os.name,
        "platform": platform.platform(),
        "windows_release": platform.release(),
        "windows_version": platform.version(),
        "python": platform.python_version(),
        "executable": sys.executable,
        "git_head": _git_head(),
        "nvidia_smi_available": shutil.which("nvidia-smi") is not None,
        "ffmpeg_available": shutil.which("ffmpeg") is not None,
        "monitor_count": monitor_count,
        "is_windows": os.name == "nt",
    }


def selected_cases(
    *,
    include_session_ending: bool = False,
    monitor_count: int | None = None,
) -> list[SmokeCase]:
    result = []
    for case in SMOKE_CASES:
        if case.session_ending and not include_session_ending:
            continue
        if case.requires_two_monitors and monitor_count is not None and monitor_count < 2:
            continue
        result.append(case)
    return result


def build_report(
    diagnostics: dict,
    results: Iterable[SmokeResult],
    *,
    include_session_ending: bool,
) -> dict:
    rows = [asdict(item) for item in results]
    counts = {state: sum(row["result"] == state for row in rows) for state in VALID_RESULTS}
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "include_session_ending": bool(include_session_ending),
        "diagnostics": diagnostics,
        "counts": counts,
        "results": rows,
    }


def _ask_result(case: SmokeCase) -> SmokeResult:
    print("\n" + "=" * 72)
    print(f"[{case.area}] {case.title}")
    print(f"ID: {case.case_id}")
    for index, instruction in enumerate(case.instructions, start=1):
        print(f"  {index}. {instruction}")

    while True:
        raw = input("Result [p=PASS / f=FAIL / s=SKIP / q=save+quit]: ").strip().lower()
        if raw == "q":
            raise KeyboardInterrupt
        mapping = {"p": "pass", "f": "fail", "s": "skip"}
        result = mapping.get(raw)
        if result:
            break
        print("Use p, f, s or q.")

    note = input("Note (optional): ").strip()
    return SmokeResult(case_id=case.case_id, result=result, note=note)


def write_report(report: dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Interactive Ziren 1.0 Windows smoke checklist. The script itself "
            "does not execute PC-control actions; it records manual verification results."
        ),
    )
    parser.add_argument(
        "--include-session-ending",
        action="store_true",
        help="Include lock/sleep/restart/shutdown verification cases. Hidden by default.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List selected smoke cases without starting the interactive checklist.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="JSON report path. Defaults to build/release-smoke/<timestamp>.json.",
    )
    args = parser.parse_args()

    diagnostics = collect_safe_diagnostics()
    cases = selected_cases(
        include_session_ending=args.include_session_ending,
        monitor_count=diagnostics.get("monitor_count"),
    )

    if args.list:
        for case in cases:
            suffix = " [SESSION ENDING]" if case.session_ending else ""
            print(f"{case.case_id}: {case.title}{suffix}")
        return 0

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_path = args.output or DEFAULT_REPORT_DIR / f"windows-smoke-{timestamp}.json"

    print("Ziren 1.0 Windows release smoke")
    print("This checklist records results only; it does not execute assistant actions.")
    print(json.dumps(diagnostics, ensure_ascii=False, indent=2))
    if not diagnostics["is_windows"]:
        print("WARNING: this release smoke is intended for the target Windows machine.")

    results: list[SmokeResult] = []
    try:
        for case in cases:
            results.append(_ask_result(case))
    except (KeyboardInterrupt, EOFError):
        print("\nChecklist stopped; saving partial report.")

    report = build_report(
        diagnostics,
        results,
        include_session_ending=args.include_session_ending,
    )
    write_report(report, output_path)
    print(f"Report: {output_path}")

    return 1 if any(item.result == "fail" for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
