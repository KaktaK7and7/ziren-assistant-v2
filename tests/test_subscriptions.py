import unittest

from app.api.command_route_client import SemanticCommandResult
from app.features.feature_gate import FeatureGate
from app.features.plans import Plan
from app.modules.base import AssistantModule, ModuleResponse
from app.router.command_router import CommandRouter


class SettingsStore:
    def get(self):
        return {
            "melissa_command_mode_enabled": True,
            "snake_command_mode_enabled": True,
        }


class FakeModule(AssistantModule):
    feature_id = "system.fake"
    display_name = "Fake"
    plan = Plan.FREE
    default_trigger_groups = {
        "fake.run": {
            "display_name": "Run",
            "triggers": ["сделай тест"],
            "argument_hint": "",
        }
    }

    def can_handle(self, text):
        return text == "сделай тест"

    def handle(self, text):
        return ModuleResponse(text="done")


class Registry:
    def __init__(self):
        self.module = FakeModule()

    def all(self):
        return [self.module]

    def get_ai_capabilities(self):
        return [{
            "feature_id": "system.fake",
            "actions": [{"action_id": "fake.run"}],
        }]

    def get_module_by_feature_id(self, feature_id):
        return self.module if feature_id == "system.fake" else None

    def execute_action(self, feature_id, action_id, arguments=None):
        return None


class SemanticSubscriptionDenied:
    def resolve(self, message, capabilities):
        return SemanticCommandResult(
            matched=False,
            command_like=True,
            reason=(
                "subscription:melissa_requires_subscription:"
                "Мелисса доступна на тарифах Plus и Pro. "
                "Змея и локальные команды остаются бесплатными."
            ),
        )


class SubscriptionTests(unittest.TestCase):
    def test_plan_hierarchy(self):
        free = FeatureGate(Plan.FREE)
        plus = FeatureGate(Plan.PLUS)
        pro = FeatureGate(Plan.PRO)

        self.assertTrue(free.is_allowed("x", Plan.FREE))
        self.assertFalse(free.is_allowed("x", Plan.PLUS))
        self.assertTrue(plus.is_allowed("x", Plan.PLUS))
        self.assertFalse(plus.is_allowed("x", Plan.PRO))
        self.assertTrue(pro.is_allowed("x", Plan.FREE))
        self.assertTrue(pro.is_allowed("x", Plan.PLUS))
        self.assertTrue(pro.is_allowed("x", Plan.PRO))

    def test_subscription_denial_never_uses_local_melissa_fallback(self):
        router = CommandRouter(
            registry=Registry(),
            feature_gate=FeatureGate(),
            settings_store=SettingsStore(),
            semantic_client=SemanticSubscriptionDenied(),
        )
        result = router.route_explicit("сделай тест")
        self.assertIsNotNone(result)
        self.assertEqual(result.module.feature_id, "system.command_router")
        self.assertIn("Plus", result.response.text)
        self.assertIn("Змея", result.response.text)
        self.assertNotEqual(result.response.text, "done")


if __name__ == "__main__":
    unittest.main()
