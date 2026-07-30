import unittest

from app.features.feature_gate import FeatureGate
from app.features.plans import Plan
from app.modules.base import AssistantModule, ModuleResponse
from app.router.command_router import CommandRouter


class FakeModule(AssistantModule):
    feature_id = "system.fake"
    display_name = "Тестовая функция"
    plan = Plan.FREE
    default_triggers = ["открой", "запусти"]

    def can_handle(self, text: str) -> bool:
        return "открой" in text or "запусти" in text

    def handle(self, text: str) -> ModuleResponse:
        return ModuleResponse(text=f"Выполнено: {text}")


class FakeRegistry:
    def __init__(self) -> None:
        self.module = FakeModule()

    def all(self) -> list[AssistantModule]:
        return [self.module]


class CommandRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.router = CommandRouter(
            registry=FakeRegistry(),
            feature_gate=FeatureGate(),
        )

    def test_explicit_route_accepts_command_at_start(self) -> None:
        result = self.router.route_explicit("  ОТКРОЙ браузер ")

        self.assertIsNotNone(result)
        self.assertEqual(result.module.feature_id, "system.fake")

    def test_explicit_route_rejects_trigger_inside_question(self) -> None:
        self.assertIsNone(
            self.router.route_explicit("расскажи, как открыть браузер"),
        )

    def test_regular_command_mode_keeps_existing_flexible_matching(self) -> None:
        self.assertIsNotNone(
            self.router.route("пожалуйста открой браузер"),
        )


if __name__ == "__main__":
    unittest.main()
