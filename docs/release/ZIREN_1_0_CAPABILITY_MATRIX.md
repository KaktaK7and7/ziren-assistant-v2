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
| Keyboard | Enter / Tab / Escape / Backspace / Delete / arrows | 🟡 NEEDS FIX | Vosk alias matrix + native SendInput test |
| Keyboard | Ctrl/Alt/Win hotkeys | 🟡 NEEDS FIX | curated whitelist smoke-test |
| Windows | Open/focus/minimize/maximize window | 🟡 NEEDS FIX | multi-app title resolver smoke-test |
| Windows | Graceful close window | 🟡 NEEDS FIX | WM_CLOSE on Explorer + normal apps; no process kill |
| Desktops | previous / next / create | 🟡 NEEDS FIX | repeated transition smoke-test |
| Desktops | address desktop 1..N | 🟡 NEEDS FIX | 1→2→1→3 deterministic smoke-test |
| Explorer | Downloads/Documents/Desktop/Pictures/Videos/Music | 🟡 NEEDS FIX | known-folder open tests |
| Screenshots | capture screenshot | 🟡 NEEDS FIX | save file + announce success only after actual save |
| Screenshots | open screenshot folder | 🟡 NEEDS FIX | fixed Pictures/Ziren/Screenshots path smoke-test |
| Recording | start/stop screen recording | 🟡 NEEDS FIX | Game Bar availability detection + actual output file check |
| Recording | open recordings folder | 🔴 NOT SHIPPING | implement fixed destination resolver |
| Audio | volume / mute | 🟡 NEEDS FIX | pycaw device smoke-test + unavailable-device honesty |
| Display | brightness | 🟡 NEEDS FIX | DDC/CI monitor support detection + per-monitor test |
| Displays | move window between monitors | 🟡 NEEDS FIX | multi-monitor smoke-test |
| System | GPU temperature | ✅ RELEASE READY | concise numeric response + nvidia-smi absence path covered |
| System | CPU temperature | 🔴 NOT SHIPPING | ship only with reliable sensor backend |
| Power | lock | 🟡 NEEDS FIX | Windows smoke-test |
| Power | sleep/restart/shutdown | 🟡 NEEDS FIX | explicit confirmation + timeout + cancellation tests |
| Productivity | reminders | 🟡 NEEDS FIX | survive restart + due while TTS active |
| Productivity | alarms | 🟡 NEEDS FIX | survive restart + audible delivery smoke-test |
| Clipboard | copy/read/paste actions | 🟡 NEEDS FIX | Snake + Melissa structured-action smoke-test |
| Social | direct text message | 🟡 NEEDS FIX | accepted-friend + ambiguity safety regression |
| Social | screenshot/clipboard send | 🟡 NEEDS FIX | accepted-friend + binary upload regression |
| Melissa | semantic action selection | 🟡 NEEDS FIX | command-like failure must never fall through to fake chat confirmation |
| Snake | custom trigger execution | 🟡 NEEDS FIX | every trigger-backed module must read TriggerStore at execution time |

## 1.0 hard rules

1. A capability cannot move to RELEASE READY because the UI exists; the local action must actually execute successfully.
2. Melissa may describe an action as completed only after Core returns a successful local execution result.
3. Snake never requires cloud AI and must remain usable if the AI service or subscription is unavailable.
4. A risky or session-ending action must have an explicit confirmation path.
5. If Windows/hardware does not support a capability, Ziren must report that limitation instead of saying it succeeded.
6. Any action advertised on the website must exist in the Core capability registry and have a non-red release status.

## Next test batch

1. Keyboard aliases and Unicode typing.
2. Window close/focus behavior.
3. Virtual desktop deterministic addressing.
4. Screenshot capture + screenshot folder.
5. Recording output/folder.
6. Reminders/alarms persistence.
7. Power confirmation safety.
8. Multi-monitor brightness/move behavior.

The matrix should be updated after every Windows smoke-test. No P0 release candidate is approved while any advertised capability remains 🔴 or has an unresolved destructive-action bug.
