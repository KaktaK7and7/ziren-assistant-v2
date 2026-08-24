# Ziren 1.0 — Capability Release Matrix

This file is the release-facing source of truth for Windows-control readiness.

Status legend:
- ✅ RELEASE READY — capability has a stable action contract and regression coverage; still requires final Windows smoke-test before 1.0.
- 🟡 NEEDS FIX — capability exists but has known gaps, incomplete aliases, platform variance, or missing end-to-end coverage.
- 🔴 NOT SHIPPING — do not advertise or expose as a 1.0 promise until implemented and tested.

## P0 matrix

| Area | Capability | Status | Release gate |
| --- | --- | --- | --- |
| Keyboard | Unicode text input | 🟡 NEEDS FIX | Notepad + Chromium + standard Win32 field smoke-test |
| Keyboard | Enter / Tab / Escape / Backspace / Delete / arrows / Home / End / Page Up/Down | ✅ RELEASE READY | Vosk alias matrix + native SendInput regressions covered; final real-app smoke-test |
| Keyboard | F1–F12 | ✅ RELEASE READY | Snake keeps explicit F1–F12 triggers; Melissa uses bounded `keyboard.function_key` 1..12; final real-app smoke-test |
| Keyboard | Ctrl/Alt/Win hotkeys | 🟡 NEEDS FIX | curated whitelist smoke-test |
| Windows | Open/focus/minimize/maximize window | 🟡 NEEDS FIX | multi-app title resolver smoke-test |
| Windows | Graceful close window | ✅ RELEASE READY | `WM_CLOSE` only, stale HWND rejection and failed `PostMessageW` covered; final Explorer + normal-app smoke-test |
| Windows | Show desktop | ✅ RELEASE READY | shell-free whitelisted Win+D path covered; final Windows smoke-test |
| Desktops | previous / next / create / close | 🟡 NEEDS FIX | repeated transition smoke-test |
| Desktops | address desktop 1..N | 🟡 NEEDS FIX | deterministic 1→2→1→3 real Windows smoke-test |
| Explorer | Downloads/Documents/Desktop/Pictures/Videos/Music | ✅ RELEASE READY | Windows Known Folder API + per-folder fallback covered; final OneDrive/redirection smoke-test |
| Explorer | latest download reveal/open | ✅ RELEASE READY | partial-download filtering + safe-extension allowlist regressions; final Explorer smoke-test |
| Screenshots | capture screenshot | ✅ RELEASE READY | atomic JPEG validation + file existence/size verification covered; final real capture smoke-test |
| Screenshots | open screenshot folder | ✅ RELEASE READY | fixed Pictures/Ziren/Screenshots action covered; final Windows smoke-test |
| Recording | start/stop screen recording | 🟡 NEEDS FIX | Game Bar state is not yet verifiable; Ziren must only report command delivery until state-aware backend exists |
| Recording | open recordings folder | ✅ RELEASE READY | safe Videos/Captures action covered; final Windows smoke-test |
| Audio | volume / mute | 🟡 NEEDS FIX | pycaw device smoke-test + unavailable-device honesty |
| Display | brightness | ✅ RELEASE READY | DDC/CI SetMonitorBrightness is followed by bounded read-back verification; final supported/unsupported physical-monitor smoke-test |
| Displays | move window between monitors | ✅ RELEASE READY | second-monitor preflight + foreground HWND + `MonitorFromWindow` post-action verification covered; final physical multi-monitor smoke-test |
| System | GPU temperature | ✅ RELEASE READY | concise numeric response + nvidia-smi absence path covered |
| System | CPU temperature | 🔴 NOT SHIPPING | ship only with reliable sensor backend |
| Power | lock | 🟡 NEEDS FIX | Windows smoke-test |
| Power | sleep/restart/shutdown | ✅ RELEASE READY | explicit request/confirm/cancel/expiry regressions covered; final manual Windows smoke-test only |
| Productivity | reminders | ✅ RELEASE READY | persisted store + at-least-once delivery + failed-TTS retry regressions; final restart/TTS smoke-test |
| Productivity | alarms | 🟡 NEEDS FIX | persisted path exists; audible winsound + real restart delivery smoke-test still required |
| Clipboard | copy/read/paste actions | 🟡 NEEDS FIX | Snake + Melissa structured-action smoke-test |
| Social | direct text message | 🟡 NEEDS FIX | accepted-friend + ambiguity safety regression |
| Social | screenshot/clipboard send | 🟡 NEEDS FIX | accepted-friend + binary upload regression |
| Melissa | semantic action selection | 🟡 NEEDS FIX | command-like failure must never fall through to fake chat confirmation; full-catalog smoke-test |
| Snake | custom trigger execution | 🟡 NEEDS FIX | route metadata is now preserved; still verify every trigger-backed module reads TriggerStore at execution time |

## 1.0 hard rules

1. A capability cannot move to RELEASE READY because the UI exists; the local action must actually execute successfully.
2. Melissa may describe an action as completed only after Core returns a successful local execution result.
3. Snake never requires cloud AI and must remain usable if the AI service or subscription is unavailable.
4. A risky or session-ending action must have an explicit confirmation path.
5. If Windows/hardware does not support a capability, Ziren must report that limitation instead of saying it succeeded.
6. Any action advertised on the website must exist in the Core capability registry and have a non-red release status.
7. `melissa_semantic` and `snake_triggers` are capability-contract metadata. User trigger customization must never erase or change these route boundaries.
8. A command that only sends a Windows hotkey may report command delivery, but must not claim the resulting state unless Core can verify that state.

## Automated P0 evidence added in the release branch

- Keyboard/Vosk alias matrix, bounded Melissa F-key action and route-boundary regression.
- Power request/confirmation/expiry/cancel safety tests.
- Reminder at-least-once delivery and failed-TTS retry tests.
- Graceful window-close tests proving ordinary close uses `WM_CLOSE`, never process termination.
- Stale HWND and foreground-focus failure tests to prevent false success.
- Shell-free Show Desktop through the whitelisted SendInput path.
- Screenshot JPEG validation, atomic write and on-disk verification.
- Recording response contract explicitly forbidding unverified start/stop claims.
- Multi-monitor move verification via actual monitor-handle change.
- DDC/CI brightness read-back verification; a successful setter call alone is not treated as success.
- Windows Known Folder API resolution and download executable/partial-file safety tests.

## Next manual smoke batch

1. Unicode typing in Notepad, Chromium and a standard Win32 field.
2. Window focus/minimize/maximize/restore across Explorer, Notepad and Chromium.
3. Virtual desktop transitions and deterministic address-by-number behavior.
4. Real screenshot capture + folder open on the target Windows 10 machine.
5. Game Bar recording behavior; do not promote start/stop until state can be verified.
6. Reminder/alarm delivery across Core restart and while TTS is busy.
7. Power lock + one carefully controlled sleep/restart confirmation test.
8. DDC/CI brightness on supported and unsupported displays.
9. Physical two-monitor left/right move verification.
10. OneDrive/redirection test for Desktop/Documents/Pictures.

The matrix should be updated after every Windows smoke-test. No P0 release candidate is approved while any advertised capability remains 🔴 or has an unresolved destructive-action bug.
