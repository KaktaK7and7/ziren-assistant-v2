import unittest
from unittest.mock import patch

from app.modules.system.keyboard_module import SystemKeyboardModule
from app.settings.trigger_store import TriggerStore


class TriggerRouteMetadataReleaseTests(unittest.TestCase):
    def test_custom_triggers_preserve_snake_only_semantic_boundary(self):
        store = TriggerStore()
        module = SystemKeyboardModule()
        module.set_trigger_store(store)

        stored = {
            "system.keyboard": {
                "keyboard.f1": ["моя клавиша один"],
                "keyboard.enter": ["подтверди поле"],
            }
        }
        with patch.object(store, "load", return_value=stored):
            groups = module.get_trigger_groups()
            self.assertEqual(module.get_action_triggers("keyboard.f1"), ["моя клавиша один"])
            self.assertEqual(module.get_action_triggers("keyboard.enter"), ["подтверди поле"])

        self.assertFalse(groups["keyboard.f1"]["melissa_semantic"])
        self.assertTrue(groups["keyboard.f1"]["snake_triggers"])
        self.assertTrue(groups["keyboard.enter"]["melissa_semantic"])
        self.assertTrue(groups["keyboard.enter"]["snake_triggers"])

    def test_semantic_only_function_key_has_no_snake_trigger_route(self):
        module = SystemKeyboardModule()
        groups = module.get_trigger_groups()

        self.assertTrue(groups["keyboard.function_key"]["melissa_semantic"])
        self.assertFalse(groups["keyboard.function_key"]["snake_triggers"])
        self.assertEqual(module.get_action_triggers("keyboard.function_key"), [])


if __name__ == "__main__":
    unittest.main()
