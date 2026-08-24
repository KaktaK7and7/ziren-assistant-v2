import unittest

from app.modules.registry import (
    MAX_AI_ACTIONS_PER_FEATURE,
    MAX_AI_ARGUMENT_HINT_LENGTH,
    MAX_AI_VOICE_EXAMPLES_PER_ACTION,
    create_default_registry,
)


class CapabilityPipelineReleaseTests(unittest.TestCase):
    def test_every_feature_fits_gateway_action_limit(self):
        catalog = create_default_registry().get_ai_capabilities()
        self.assertTrue(catalog)
        for feature in catalog:
            with self.subTest(feature=feature["feature_id"]):
                self.assertLessEqual(
                    len(feature["actions"]),
                    MAX_AI_ACTIONS_PER_FEATURE,
                )

    def test_voice_examples_are_structured_not_hidden_in_argument_hint(self):
        catalog = create_default_registry().get_ai_capabilities()
        keyboard = next(
            feature for feature in catalog if feature["feature_id"] == "system.keyboard"
        )
        enter = next(
            action for action in keyboard["actions"] if action["action_id"] == "keyboard.enter"
        )

        self.assertIn("нажми интер", enter["voice_examples"])
        self.assertLessEqual(
            len(enter["voice_examples"]),
            MAX_AI_VOICE_EXAMPLES_PER_ACTION,
        )
        self.assertLessEqual(len(enter["argument_hint"]), MAX_AI_ARGUMENT_HINT_LENGTH)
        self.assertNotIn("Голосовые примеры", enter["argument_hint"])

    def test_keyboard_semantic_catalog_remains_compact(self):
        catalog = create_default_registry().get_ai_capabilities()
        keyboard = next(
            feature for feature in catalog if feature["feature_id"] == "system.keyboard"
        )
        action_ids = {action["action_id"] for action in keyboard["actions"]}

        self.assertIn("keyboard.function_key", action_ids)
        self.assertIn("keyboard.desktop_number", action_ids)
        self.assertNotIn("keyboard.f1", action_ids)
        self.assertNotIn("keyboard.f12", action_ids)
        self.assertLessEqual(len(action_ids), MAX_AI_ACTIONS_PER_FEATURE)


if __name__ == "__main__":
    unittest.main()
