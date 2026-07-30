import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.settings.companion_store import CompanionSettingsStore


class CompanionSettingsStoreTests(unittest.TestCase):
    def test_proactive_dialogue_is_opt_in_and_values_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings_path = Path(directory) / "companion.json"

            with patch(
                "app.settings.companion_store.COMPANION_SETTINGS_FILE",
                settings_path,
            ):
                store = CompanionSettingsStore()
                defaults = store.get()
                updated = store.update({
                    "proactive_dialogue_enabled": True,
                    "command_reaction_chance": 5,
                    "quiet_hours_start": 99,
                    "unknown": "ignored",
                })

            self.assertFalse(defaults["proactive_dialogue_enabled"])
            self.assertTrue(updated["proactive_dialogue_enabled"])
            self.assertEqual(updated["command_reaction_chance"], 1.0)
            self.assertEqual(updated["quiet_hours_start"], 23)
            self.assertNotIn("unknown", updated)


if __name__ == "__main__":
    unittest.main()
