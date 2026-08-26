from __future__ import annotations

import unittest
from unittest.mock import patch

from app.media_control.models import MediaActionResult
from app.media_control.windows_media import open_url
from app.modules.system.media_control_module import SystemMediaControlModule


class _FakeStore:
    def find_by_query(self, query):
        return object() if query == "моя волна" else None


class _FakeResolver:
    def __init__(self):
        self.store = _FakeStore()
        self.basic_calls = []
        self.preset_calls = []

    def perform_basic(self, action):
        self.basic_calls.append(action)
        return MediaActionResult("success", "legacy success")

    def play_preset(self, query):
        self.preset_calls.append(query)
        return MediaActionResult("success", "Открываю мою волну")


class MediaReleaseTests(unittest.TestCase):
    def test_basic_media_action_reports_delivery_not_verified_playback_state(self):
        resolver = _FakeResolver()
        module = SystemMediaControlModule(resolver=resolver)

        response = module.handle("следующий трек")

        self.assertEqual(resolver.basic_calls, ["next"])
        self.assertIn("Передала Windows", response.text)
        self.assertNotIn("Включаю следующий трек", response.text)

    def test_custom_media_trigger_is_used_by_real_execution_path(self):
        resolver = _FakeResolver()
        module = SystemMediaControlModule(resolver=resolver)

        class FakeTriggerStore:
            def get_feature_groups(self, feature_id, defaults):
                groups = {
                    action_id: dict(group, triggers=list(group.get("triggers", [])))
                    for action_id, group in defaults.items()
                }
                groups["media.next"]["triggers"] = ["листай музыку"]
                return groups

        module.set_trigger_store(FakeTriggerStore())
        response = module.handle("листай музыку")

        self.assertEqual(resolver.basic_calls, ["next"])
        self.assertIn("Передала Windows", response.text)

    def test_open_url_rejects_failed_browser_handoff(self):
        with patch("app.media_control.windows_media.webbrowser.open", return_value=False):
            with self.assertRaises(RuntimeError):
                open_url("https://example.com")

    def test_open_url_accepts_confirmed_browser_handoff(self):
        with patch("app.media_control.windows_media.webbrowser.open", return_value=True) as opener:
            open_url("https://example.com")

        opener.assert_called_once_with("https://example.com")


if __name__ == "__main__":
    unittest.main()
