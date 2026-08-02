import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.settings.companion_store import CompanionSettingsStore


class CompanionSettingsStoreTests(unittest.TestCase):
    def test_proactive_dialogue_defaults_on_but_can_be_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings_path = Path(directory) / "companion.json"

            with patch(
                "app.settings.companion_store.COMPANION_SETTINGS_FILE",
                settings_path,
            ):
                store = CompanionSettingsStore()
                defaults = store.get()
                updated = store.update({
                    "proactive_dialogue_enabled": False,
                    "command_reaction_chance": 5,
                    "quiet_hours_start": 99,
                    "unknown": "ignored",
                })

            self.assertTrue(defaults["proactive_dialogue_enabled"])
            self.assertEqual(defaults["proactive_idle_min_minutes"], 12)
            self.assertEqual(defaults["proactive_idle_max_minutes"], 30)
            self.assertFalse(updated["proactive_dialogue_enabled"])
            self.assertEqual(updated["command_reaction_chance"], 1.0)
            self.assertEqual(updated["quiet_hours_start"], 23)
            self.assertNotIn("unknown", updated)


if __name__ == "__main__":
    unittest.main()
