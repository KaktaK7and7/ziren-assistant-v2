import copy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from app.api.social_client import SocialApiError
from app.features.feature_gate import FeatureGate
from app.features.plans import Plan
from app.modules.base import AssistantModule, ModuleResponse
from app.modules.system.social_messaging_module import SystemSocialMessagingModule
from app.router.command_router import CommandRouter
from app.settings.trigger_store import TriggerStore


class _Settings:
    def get(self):
        return {
            "snake_command_mode_enabled": True,
            "melissa_command_mode_enabled": True,
        }


class _BroadModule(AssistantModule):
    feature_id = "test.broad"
    display_name = "Broad"
    plan = Plan.FREE
    default_trigger_groups = {
        "broad.run": {
            "display_name": "Broad",
            "triggers": ["напиши"],
        }
    }

    def can_handle(self, text: str) -> bool:
        return "напиши" in text

    def handle(self, text: str) -> ModuleResponse:
        return ModuleResponse(text="broad")


class _SpecificModule(AssistantModule):
    feature_id = "test.specific"
    display_name = "Specific"
    plan = Plan.FREE
    default_trigger_groups = {
        "specific.run": {
            "display_name": "Specific",
            "triggers": ["напиши здесь"],
        }
    }

    def can_handle(self, text: str) -> bool:
        return "напиши здесь" in text

    def handle(self, text: str) -> ModuleResponse:
        return ModuleResponse(text="specific")


class _Registry:
    def __init__(self, modules):
        self._modules = modules

    def all(self):
        return list(self._modules)


class SnakeRoutingSpecificityTests(unittest.TestCase):
    def test_longer_specific_trigger_wins_even_when_broad_module_is_registered_first(self):
        router = CommandRouter(
            registry=_Registry([_BroadModule(), _SpecificModule()]),
            feature_gate=FeatureGate(),
            settings_store=_Settings(),
        )

        result = router.route("напиши здесь привет")

        self.assertIsNotNone(result)
        self.assertEqual(result.module.feature_id, "test.specific")
        self.assertEqual(result.response.text, "specific")

    def test_trigger_specificity_ignores_punctuation_and_yo_difference(self):
        specific = _SpecificModule()
        score = CommandRouter._module_trigger_score(
            specific,
            "НАПИШИ, ЗДЕСЬ привет",
        )
        self.assertGreaterEqual(score, 20_000)


class SocialCustomTriggerTests(unittest.TestCase):
    @staticmethod
    def _module(action_id: str, custom_trigger: str):
        client = Mock()
        friend = SimpleNamespace(id=7, voice_name="Диана", username="Diana")

        def resolve_friend(spoken: str):
            if spoken.strip().lower() == "диане":
                return friend
            raise SocialApiError("friend not found")

        client.resolve_friend.side_effect = resolve_friend
        module = SystemSocialMessagingModule(client=client, start_inbox_listener=False)
        trigger_store = Mock(spec=TriggerStore)

        def get_groups(_feature_id, defaults):
            groups = copy.deepcopy(defaults)
            groups[action_id]["triggers"] = [custom_trigger]
            return groups

        trigger_store.get_groups.side_effect = get_groups
        module.set_trigger_store(trigger_store)
        return module, client, friend

    def test_custom_text_message_trigger_is_used_for_real_parser(self):
        module, client, friend = self._module("social.message.text", "скажи другу")

        self.assertTrue(module.can_handle("скажи другу диане привет брат"))
        command = module._parse_command("скажи другу диане привет брат")

        self.assertEqual(command.kind, "text")
        self.assertEqual(command.friend, friend)
        self.assertEqual(command.body, "привет брат")
        client.resolve_friend.assert_called()

    def test_custom_screenshot_trigger_does_not_need_hardcoded_screenshot_word(self):
        module, _client, friend = self._module(
            "social.message.screenshot",
            "закинь картинку другу",
        )

        self.assertTrue(module.can_handle("закинь картинку другу диане"))
        command = module._parse_command("закинь картинку другу диане")

        self.assertEqual(command.kind, "screenshot")
        self.assertEqual(command.friend, friend)

    def test_custom_clipboard_trigger_does_not_need_hardcoded_copy_word(self):
        module, _client, friend = self._module(
            "social.message.clipboard",
            "закинь буфер другу",
        )

        self.assertTrue(module.can_handle("закинь буфер другу диане"))
        command = module._parse_command("закинь буфер другу диане")

        self.assertEqual(command.kind, "clipboard")
        self.assertEqual(command.friend, friend)


if __name__ == "__main__":
    unittest.main()
