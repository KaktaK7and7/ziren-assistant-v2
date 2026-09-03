# Ziren 1.0 — Capability Release Matrix

This file is the release-facing source of truth for Windows-control readiness.

Status legend:
- ✅ RELEASE READY — capability has a stable action contract and regression coverage; still requires final Windows smoke-test before 1.0.
- 🟡 NEEDS FIX — capability exists but has known gaps, incomplete aliases, platform variance, or missing end-to-end coverage.
- 🔴 NOT SHIPPING — do not advertise or expose as a 1.0 promise until implemented and tested.

## P0 matrix

| Area | Capability | Status | Release gate |
| --- | --- | --- | --- |
| Apps | Launch known app / game | ✅ RELEASE READY | AppResolver resolves only known targets; `.exe`/`.lnk` validation, `shell=False`, elevation result checks and URL browser-handoff verification covered; final Notepad/Discord/Steam smoke |
| Browser | Tab/navigation hotkeys | ✅ RELEASE READY | foreground process must be an allowlisted browser before any hotkey; only whitelisted hotkeys are sent and response reports delivery rather than unverified tab state; final Chromium/Firefox smoke |
| Media | Global play/pause/next/previous/stop | 🟡 NEEDS FIX | Windows media-key delivery is truthful, but Core cannot yet verify that an active media session changed playback state; Spotify/browser-media smoke and state-aware backend decision required |
| Media | Open saved music preset | ✅ RELEASE READY | preset must resolve locally and browser handoff must return success; no autoplay claim; final browser smoke |
| Keyboard | Unicode text input | 🟡 NEEDS FIX | SendInput Unicode path is bounded and truthful, but Notepad + Chromium + standard Win32 field smoke-test is still required |
| Keyboard | Enter / Tab / Escape / Backspace / Delete / arrows / Home / End / Page Up/Down | ✅ RELEASE READY | Vosk alias matrix + native SendInput regressions covered; final real-app smoke-test |
| Keyboard | F1–F12 | ✅ RELEASE READY | Snake keeps explicit F1–F12 triggers; Melissa uses bounded `keyboard.function_key` 1..12; final real-app smoke-test |
| Keyboard | Ctrl/Alt/Win hotkeys | ✅ RELEASE READY | curated whitelist + native packet layout + post-hotkey Shell settle regression covered; final real-app smoke-test |
| Windows | Open/focus/minimize/maximize window | 🟡 NEEDS FIX | multi-app title resolver smoke-test |
| Windows | Graceful close window | ✅ RELEASE READY | `WM_CLOSE` only, stale HWND rejection and failed `PostMessageW` covered; final Explorer + normal-app smoke-test |
| Windows | Show desktop | ✅ RELEASE READY | shell-free whitelisted Win+D path covered; final Windows smoke-test |
| Desktops | previous / next / create / close | 🟡 NEEDS FIX | Shell hotkeys now get a settle interval; repeated transition smoke-test still required |
| Desktops | address desktop 1..N | 🟡 NEEDS FIX | semantic absolute action + paced hotkeys covered; deterministic 1→2→1→3 real Windows smoke-test still required |
| Explorer | Downloads/Documents/Desktop/Pictures/Videos/Music | ✅ RELEASE READY | Windows Known Folder API + per-folder fallback covered; final OneDrive/redirection smoke-test |
| Explorer | latest download reveal/open | ✅ RELEASE READY | partial-download filtering + safe-extension allowlist regressions; final Explorer smoke-test |
| Screenshots | capture screenshot | ✅ RELEASE READY | atomic JPEG validation + file existence/size verification covered; final real capture smoke-test |
| Screenshots | open screenshot folder | ✅ RELEASE READY | fixed Pictures/Ziren/Screenshots action covered; final Windows smoke-test |
| Recording | start/stop screen recording | 🟡 NEEDS FIX | Game Bar state is not yet verifiable; Ziren must only report command delivery until state-aware backend exists |
| Recording | open recordings folder | ✅ RELEASE READY | safe Videos/Captures action covered; final Windows smoke-test |
| Audio | volume / mute | ✅ RELEASE READY | pycaw endpoint lookup + set/mute read-back verification + false-success regressions covered; final physical audio-device smoke-test |
| Display | brightness | ✅ RELEASE READY | DDC/CI SetMonitorBrightness is followed by bounded read-back verification; final supported/unsupported physical-monitor smoke-test |
| Displays | move window between monitors | ✅ RELEASE READY | second-monitor preflight + foreground HWND + `MonitorFromWindow` post-action verification covered; final physical multi-monitor smoke-test |
| System | GPU temperature | ✅ RELEASE READY | concise numeric response + nvidia-smi absence path covered |
| System | CPU temperature | 🔴 NOT SHIPPING | ship only with reliable sensor backend |
| Power | lock | 🟡 NEEDS FIX | WinAPI return value is checked, but final Windows smoke-test remains |
| Power | sleep/restart/shutdown | ✅ RELEASE READY | explicit request/confirm/cancel/expiry regressions covered; final manual Windows smoke-test only |
| Productivity | reminders | ✅ RELEASE READY | persisted store + at-least-once delivery + failed-TTS retry regressions; final restart/TTS smoke-test |
| Productivity | alarms | ✅ RELEASE READY | persisted restart model + in-flight cancellation + non-acknowledgement safety covered; final audible Windows smoke-test |
| Clipboard | read / write | ✅ RELEASE READY | exact write/read-back verification, size limits and social-route collision regression covered; final Windows clipboard smoke-test |
| Text input | Unicode typing action | 🟡 NEEDS FIX | Snake and Melissa use the same bounded backend and do not claim app acceptance; final Notepad/Chromium/Win32 smoke-test |
| Social | direct text message | 🟡 NEEDS FIX | accepted-friend + ambiguity safety regression |
| Social | screenshot/clipboard send | 🟡 NEEDS FIX | accepted-friend + binary upload regression |
| Melissa | semantic action selection | ✅ RELEASE READY | Core → auth-site → AI-service catalog is bounded to 40 actions/feature, structured voice examples are preserved, fake chat fallback is blocked; final staging classifier smoke-test |
| Snake | custom trigger execution | ✅ RELEASE READY | TriggerStore-backed action groups are used by trigger-backed modules, router picks the most-specific matching trigger, and scheduler/social/file/keyboard/browser/media custom-route regressions are covered; final user-created-trigger Windows smoke-test |

## 1.0 hard rules

1. A capability cannot move to RELEASE READY because the UI exists; the local action must actually execute successfully.
2. Melissa may describe an action as completed only after Core returns a successful local execution result.
3. Snake never requires cloud AI and must remain usable if the AI service or subscription is unavailable.
4. A risky or session-ending action must have an explicit confirmation path.
5. If Windows/hardware does not support a capability, Ziren must report that limitation instead of saying it succeeded.
6. Any action advertised on the website must exist in the Core capability registry and have a non-red release status.
7. `melissa_semantic` and `snake_triggers` are capability-contract metadata. User trigger customization must never erase or change these route boundaries.
8. A command that only sends a Windows hotkey may report command delivery, but must not claim the resulting state unless Core can verify that state.
9. Capability limits are an end-to-end contract. Core must never advertise more semantic actions than auth-site and AI-service accept.
10. Voice/Vosk examples travel as structured `voice_examples`; do not hide them inside free-form prompt text.
11. The public website capability manifest must come from the release candidate Core `ModuleRegistry`, not from a manually maintained list.
12. Session-ending manual smoke cases are opt-in and must never be executed automatically by CI or the smoke recorder.
13. Browser hotkeys require a verified foreground browser process; generic hotkeys must never be sprayed into an unrelated active application.
14. Global media keys are delivery-only until a state-aware media-session backend verifies playback state.

## Automated P0 evidence added in the release branch

- App Launcher validates executable/shortcut targets, uses `shell=False` for process launch, checks elevation handoff and rejects failed browser URL handoff.
- Browser control verifies the foreground process against an allowlist before sending a whitelisted hotkey and never claims unverified tab/navigation state.
- Media control reports global media-key delivery rather than unverified playback state; saved presets require a confirmed browser handoff and do not claim autoplay.
- Keyboard/Vosk alias matrix, bounded Melissa F-key action and route-boundary regression.
- Native SendInput layout plus a short post-hotkey settle interval for asynchronous Windows Shell actions.
- Power request/confirmation/expiry/cancel safety tests.
- Reminder at-least-once delivery, failed-TTS retry, restart persistence model and in-flight cancellation tests.
- Graceful window-close tests proving ordinary close uses `WM_CLOSE`, never process termination.
- Stale HWND and foreground-focus failure tests to prevent false success.
- Shell-free Show Desktop through the whitelisted SendInput path.
- Screenshot JPEG validation, atomic write and on-disk verification.
- Recording response contract explicitly forbidding unverified start/stop claims.
- Multi-monitor move verification via actual monitor-handle change.
- DDC/CI brightness read-back verification; a successful setter call alone is not treated as success.
- pycaw volume/mute read-back verification and missing-endpoint honesty.
- Clipboard exact read-back verification and social-command routing collision coverage.
- Windows Known Folder API resolution and download executable/partial-file safety tests.
- Melissa capability catalog contract locked across Core, auth-site and AI-service with a 40-action limit and structured voice examples.
- Snake routing chooses the most-specific matching TriggerStore action instead of depending on module registration order.
- Scheduler and social parsers execute user-customized trigger prefixes; file, keyboard, browser, capture, text, clipboard, brightness, monitor, volume, window, media, status, power and launcher modules were audited for TriggerStore-backed matching.
- Website capability data is exported from the real Core `ModuleRegistry`; Core CI validates it and publishes `ziren-web-capabilities` as a release artifact.
- auth-site contract tests reject a hand-authored/invalid capability source, missing route flags, leaked `system.test`, or broken F-key route boundaries.
- `scripts/windows_release_smoke.py` provides a non-executing manual P0 checklist and UTF-8 JSON report; tests prove session-ending cases are hidden by default and the recorder imports no PC-control execution backend.

## Canonical manual Windows smoke

Use the release-candidate Core checkout on the target Windows machine:

```powershell
python scripts/windows_release_smoke.py --list
python scripts/windows_release_smoke.py
```

The normal run contains only non-session-ending checks. It records PASS / FAIL / SKIP plus notes into `build/release-smoke/*.json`; it does not press keys, change settings, lock, sleep, restart or shut down the PC itself.

Only after all work is saved and the normal batch is complete, explicitly opt in to the power-session cases:

```powershell
python scripts/windows_release_smoke.py --include-session-ending
```

`lock`, `sleep`, `restart` and `shutdown` are hidden unless that flag is supplied. A release candidate is not approved while an applicable P0 smoke case is FAIL. A SKIP must have an explicit hardware/environment reason.

## Next manual smoke batch

1. Launch known Notepad/Discord/Steam targets and verify resolver ambiguity never opens the wrong app.
2. With Chromium/Firefox foreground, test new/close/restore tab, back/forward/reload; repeat one command with Notepad foreground and verify Ziren blocks it.
3. Test global media keys against a real Spotify/browser media session and confirm Ziren only reports delivery when state cannot be verified; test a saved preset and confirm no autoplay claim.
4. Unicode typing in Notepad, Chromium and a standard Win32 edit control.
5. F1–F12 voice addressability and representative Ctrl/Alt/Win hotkeys with no stuck modifiers.
6. Clipboard write → exact read-back → paste with a Unicode sample.
7. Window focus/minimize/maximize/restore across Explorer, Notepad and Chromium, plus graceful WM_CLOSE.
8. Virtual desktop transitions and deterministic address-by-number behavior: 1→2→1→3→1.
9. Real screenshot capture + folder open on the target Windows 10 machine.
10. Game Bar recording behavior; do not promote start/stop until state can be verified.
11. Reminder/alarm delivery across Core restart and while TTS is busy; verify audible alarm and cancellation.
12. Volume/mute against the real default endpoint.
13. DDC/CI brightness on supported and unsupported displays.
14. Physical two-monitor left/right move verification when two monitors are available.
15. OneDrive/redirection test for Desktop/Documents/Pictures and safe reveal/open of the latest download.
16. At least one user-created trigger in keyboard/files/scheduler/social/browser/media to confirm editor → TriggerStore → runtime execution on the target machine.
17. Staging Melissa smoke: natural-language commands for keyboard, windows, scheduler, brightness and clipboard all select only catalog actions.
18. After saving all work, explicit lock/sleep/restart/shutdown confirmation-path smoke using `--include-session-ending`.

The matrix should be updated after every Windows smoke-test. No P0 release candidate is approved while any advertised capability remains 🔴 or has an unresolved destructive-action bug.
