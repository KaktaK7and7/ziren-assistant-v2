import unittest
from copy import deepcopy
from unittest.mock import patch

from app.api.command_route_client import SemanticCommandResult
from app.features.feature_gate import FeatureGate
from app.features.plans import Plan
from app.modules.base import AssistantModule, ModuleResponse
from app.modules.registry import create_default_registry
from app.modules.system.brightness_module import SystemBrightnessModule
from app.modules.system.file_navigation_module import SystemFileNavigationModule
from app.modules.system.keyboard_module import SystemKeyboardModule
from app.modules.system.power_control_module import SystemPowerControlModule
from app.modules.system.scheduler_module import SystemSchedulerModule
from app.modules.system.screenshot_module import SystemScreenshotModule
from app.modules.system.text_input_module import SystemTextInputModule
from app.router.command_router import CommandRouter


class InMemoryTriggerStore:
    def __init__(self, overrides=None):
        self.overrides = overrides or {}

    def get_groups(self, feature_id, default_groups):
        groups = {
            action_id: {
                "display_name": group.get("display_name", action_id),
                "triggers": list(group.get("triggers", [])),
            }
            for action_id, group in deepcopy(default_groups).items()
        }
        for action_id, triggers in self.overrides.get(feature_id, {}).items():
            if action_id in groups:
                groups[action_id]["triggers"] = list(triggers)
        return groups

    def get(self, feature_id, default):
        return list(default)


class FakeSettingsStore:
    def __init__(self, *, melissa=True, snake=True):
        self.melissa = melissa
        self.snake = snake

    def get(self):
        return {
            "melissa_command_mode_enabled": self.melissa,
            "snake_command_mode_enabled": self.snake,
        }


class StructuredFakeModule(AssistantModule):
    feature_id = "system.fake_structured"
    display_name = "Тестовая structured функция"
    plan = Plan.FREE
    default_trigger_groups = {
        "fake.run": {
            "display_name": "Выполнить тест",
            "triggers": ["выполни тест"],
            "argument_hint": "arguments.text — тестовый текст.",
        }
    }

    def __init__(self):
        self.executions = []

    def can_handle(self, text):
        return text.startswith("выполни тест")

    def handle(self, text):
        return ModuleResponse(text="local fallback")

    def execute_action(self, action_id, arguments=None):
        if action_id != "fake.run":
            return None
        self.executions.append(dict(arguments or {}))
        return ModuleResponse(text="structured executed")


class StructuredFakeRegistry:
    def __init__(self):
        self.module = StructuredFakeModule()

    def all(self):
        return [self.module]

    def get_ai_capabilities(self):
        return [
            {
                "feature_id": self.module.feature_id,
                "display_name": self.module.display_name,
                "actions": [
                    {
                        "action_id": "fake.run",
                        "display_name": "Выполнить тест",
                        "argument_hint": "arguments.text",
                    }
                ],
            }
        ]

    def get_module_by_feature_id(self, feature_id):
        return self.module if feature_id == self.module.feature_id else None

    def execute_action(self, feature_id, action_id, arguments=None):
        module = self.get_module_by_feature_id(feature_id)
        if module is None:
            return None
        response = module.execute_action(action_id, arguments)
        return (module, response) if response is not None else None


class FakeSemanticClient:
    def __init__(self, result=None, error=None):
        self.result = result or SemanticCommandResult()
        self.error = error
        self.calls = []

    def resolve(self, message, capabilities):
        self.calls.append((message, capabilities))
        if self.error:
            raise self.error
        return self.result


class ControlRoutingV2Tests(unittest.TestCase):
    def test_default_registry_contains_control_v2_capabilities(self):
        registry = create_default_registry()
        feature_ids = {module.feature_id for module in registry.all()}
        required = {
            "system.app_launcher",
            "system.window_control",
            "system.keyboard",
            "system.text_input",
            "system.clipboard",
            "system.file_navigation",
            "system.volume",
            "system.media_control",
            "system.screenshot",
            "system.screen_recording",
            "system.status",
            "system.brightness",
            "system.monitors",
            "system.scheduler",
            "system.power",
        }
        self.assertTrue(required.issubset(feature_ids), required - feature_ids)

        ai_feature_ids = {
            feature["feature_id"]
            for feature in registry.get_ai_capabilities()
        }
        self.assertTrue(required.issubset(ai_feature_ids), required - ai_feature_ids)

    def test_text_input_accepts_reported_infinitive_phrase(self):
        module = SystemTextInputModule()
        self.assertTrue(module.can_handle("напечатать текст привет брат"))
        self.assertEqual(module._extract_text("напечатать текст привет брат"), "привет брат")

    def test_snake_screenshot_accepts_short_triggers(self):
        module = SystemScreenshotModule()
        self.assertTrue(module.can_handle("скриншот"))
        self.assertTrue(module.can_handle("сделать скриншот"))
        self.assertFalse(module.can_handle("отправь скриншот диане"))

    def test_keyboard_uses_user_action_trigger(self):
        module = SystemKeyboardModule()
        module.set_trigger_store(
            InMemoryTriggerStore(
                {"system.keyboard": {"keyboard.tab": ["следующее поле"]}}
            )
        )
        action = module._find_action("следующее поле")
        self.assertIsNotNone(action)
        self.assertEqual(action[0], "tab")
        self.assertFalse(module.can_handle("нажми tab"))

    def test_file_folder_custom_trigger_keeps_folder_identity(self):
        module = SystemFileNavigationModule()
        module.set_trigger_store(
            InMemoryTriggerStore(
                {
                    "system.file_navigation": {
                        "files.folder.videos": ["мои видосы"],
                    }
                }
            )
        )
        self.assertEqual(module._find_action("мои видосы"), "files.folder.videos")

    def test_scheduler_parses_russian_relative_numbers(self):
        module = SystemSchedulerModule(start_worker=False)

        action, args = module._parse_local("напомни через две минуты проверить Ziren")
        self.assertEqual(action, "scheduler.reminder.relative")
        self.assertEqual(args["minutes"], 2)
        self.assertEqual(args["label"], "проверить Ziren")

        action, args = module._parse_local(
            "создай напоминание через двадцать пять минут проверить сборку"
        )
        self.assertEqual(action, "scheduler.reminder.relative")
        self.assertEqual(args["minutes"], 25)
        self.assertEqual(args["label"], "проверить сборку")

    def test_scheduler_supports_relative_and_spoken_clock_alarms(self):
        module = SystemSchedulerModule(start_worker=False)

        action, args = module._parse_local("будильник через две минуты")
        self.assertEqual(action, "scheduler.alarm.relative")
        self.assertEqual(args["minutes"], 2)

        action, args = module._parse_local("поставь будильник на семь тридцать")
        self.assertEqual(action, "scheduler.alarm.clock")
        self.assertEqual(args["time"], "07:30")

    def test_brightness_does_not_confuse_monitor_number_with_percent(self):
        module = SystemBrightnessModule()

        action, args = module._parse_local("какая яркость монитора 2")
        self.assertEqual(action, "brightness.get")
        self.assertEqual(args["monitor"], 2)
        self.assertNotIn("percent", args)

        action, args = module._parse_local("яркость монитора 2 40 процентов")
        self.assertEqual(action, "brightness.set")
        self.assertEqual(args["monitor"], 2)
        self.assertEqual(args["percent"], 40)

        action, args = module._parse_local("яркость второго монитора сорок процентов")
        self.assertEqual(action, "brightness.set")
        self.assertEqual(args["monitor"], 2)
        self.assertEqual(args["percent"], 40)

    def test_power_request_never_shutdowns_before_confirmation(self):
        module = SystemPowerControlModule()
        with patch(
            "app.modules.system.power_control_module.shutdown_workstation"
        ) as shutdown:
            response = module.execute_action("power.shutdown.request", {})
            self.assertIn("Подтверди", response.text)
            shutdown.assert_not_called()

            response = module.execute_action("power.confirm", {})
            self.assertIn("Выключаю", response.text)
            shutdown.assert_called_once_with()

    def test_melissa_uses_semantic_action_before_local_trigger(self):
        registry = StructuredFakeRegistry()
        semantic = FakeSemanticClient(
            SemanticCommandResult(
                matched=True,
                command_like=True,
                feature_id="system.fake_structured",
                action_id="fake.run",
                arguments={"text": "из нейросети"},
                confidence=0.96,
                reason="command: test",
            )
        )
        router = CommandRouter(
            registry=registry,
            feature_gate=FeatureGate(),
            settings_store=FakeSettingsStore(),
            semantic_client=semantic,
        )

        result = router.route_explicit("выполни тест локально")
        self.assertIsNotNone(result)
        self.assertEqual(result.response.text, "structured executed")
        self.assertEqual(registry.module.executions, [{"text": "из нейросети"}])
        self.assertEqual(len(semantic.calls), 1)

    def test_melissa_command_like_unmatched_never_falls_through_to_chat(self):
        registry = StructuredFakeRegistry()
        semantic = FakeSemanticClient(
            SemanticCommandResult(
                matched=False,
                command_like=True,
                confidence=0.55,
                reason="command: no safe match",
            )
        )
        router = CommandRouter(
            registry=registry,
            feature_gate=FeatureGate(),
            settings_store=FakeSettingsStore(),
            semantic_client=semantic,
        )

        result = router.route_explicit("нажми какую-нибудь странную кнопку")
        self.assertIsNotNone(result)
        self.assertEqual(result.module.feature_id, "system.command_router")
        self.assertIn("не нашла", result.response.text)

    def test_melissa_chat_like_message_still_goes_to_chat(self):
        registry = StructuredFakeRegistry()
        semantic = FakeSemanticClient(
            SemanticCommandResult(
                matched=False,
                command_like=False,
                reason="chat: ordinary conversation",
            )
        )
        router = CommandRouter(
            registry=registry,
            feature_gate=FeatureGate(),
            settings_store=FakeSettingsStore(),
            semantic_client=semantic,
        )
        self.assertIsNone(router.route_explicit("как у тебя дела"))

    def test_modes_can_disable_each_route_independently(self):
        registry = StructuredFakeRegistry()
        semantic = FakeSemanticClient(
            SemanticCommandResult(
                matched=True,
                command_like=True,
                feature_id="system.fake_structured",
                action_id="fake.run",
                confidence=0.99,
                reason="command: test",
            )
        )

        melissa_off = CommandRouter(
            registry=registry,
            feature_gate=FeatureGate(),
            settings_store=FakeSettingsStore(melissa=False, snake=True),
            semantic_client=semantic,
        )
        self.assertIsNone(melissa_off.route_explicit("выполни тест"))

        snake_off = CommandRouter(
            registry=registry,
            feature_gate=FeatureGate(),
            settings_store=FakeSettingsStore(melissa=True, snake=False),
            semantic_client=semantic,
        )
        self.assertIsNone(snake_off.route("выполни тест"))


if __name__ == "__main__":
    unittest.main()
