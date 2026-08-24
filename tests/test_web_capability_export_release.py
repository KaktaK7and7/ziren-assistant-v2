import os
import unittest

from app.config.settings import DESKTOP_TOKEN_ENV
from scripts.export_web_capabilities import MANIFEST_VERSION, build_web_manifest


class WebCapabilityExportReleaseTests(unittest.TestCase):
    def test_manifest_is_generated_from_real_core_registry(self):
        manifest = build_web_manifest()

        self.assertEqual(manifest["schema_version"], MANIFEST_VERSION)
        self.assertEqual(
            manifest["generated_from"],
            "ziren-assistant-v2:ModuleRegistry",
        )
        self.assertTrue(manifest["features"])
        self.assertNotIn(
            "system.test",
            {feature["feature_id"] for feature in manifest["features"]},
        )

    def test_export_keeps_snake_and_melissa_action_boundaries(self):
        manifest = build_web_manifest()
        keyboard = next(
            feature
            for feature in manifest["features"]
            if feature["feature_id"] == "system.keyboard"
        )
        actions = {action["id"]: action for action in keyboard["actions"]}

        self.assertIn("keyboard.f1", actions)
        self.assertTrue(actions["keyboard.f1"]["snake"])
        self.assertFalse(actions["keyboard.f1"]["melissa"])

        self.assertIn("keyboard.function_key", actions)
        self.assertFalse(actions["keyboard.function_key"]["snake"])
        self.assertTrue(actions["keyboard.function_key"]["melissa"])

    def test_export_contains_authenticated_social_capability_without_leaking_token(self):
        previous = os.environ.pop(DESKTOP_TOKEN_ENV, None)
        try:
            manifest = build_web_manifest(include_authenticated=True)
            feature_ids = {feature["feature_id"] for feature in manifest["features"]}
            self.assertIn("system.social_messaging", feature_ids)
            self.assertNotIn(DESKTOP_TOKEN_ENV, os.environ)
        finally:
            if previous is not None:
                os.environ[DESKTOP_TOKEN_ENV] = previous

    def test_every_exported_action_has_route_flags_and_bounded_example(self):
        manifest = build_web_manifest()
        for feature in manifest["features"]:
            with self.subTest(feature=feature["feature_id"]):
                self.assertIn("plan", feature)
                self.assertEqual(feature["status"], "testing")
                for action in feature["actions"]:
                    self.assertIsInstance(action["snake"], bool)
                    self.assertIsInstance(action["melissa"], bool)
                    self.assertLessEqual(len(action["example"]), 80)


if __name__ == "__main__":
    unittest.main()
