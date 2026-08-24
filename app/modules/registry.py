import os
from typing import Any

from app.config.settings import DESKTOP_TOKEN_ENV
from app.modules.base import AssistantModule, ModuleResponse
from app.modules.system.app_launcher_module import SystemAppLauncherModule
from app.modules.system.brightness_module import SystemBrightnessModule
from app.modules.system.browser_control_module import SystemBrowserControlModule
from app.modules.system.clipboard_module import SystemClipboardModule
from app.modules.system.file_navigation_module import SystemFileNavigationModule
from app.modules.system.keyboard_module import SystemKeyboardModule
from app.modules.system.media_control_module import SystemMediaControlModule
from app.modules.system.monitor_control_module import SystemMonitorControlModule
from app.modules.system.power_control_module import SystemPowerControlModule
from app.modules.system.scheduler_module import SystemSchedulerModule
from app.modules.system.screen_recording_module import SystemScreenRecordingModule
from app.modules.system.screenshot_module import SystemScreenshotModule
from app.modules.system.social_messaging_module import SystemSocialMessagingModule
from app.modules.system.system_status_module import SystemStatusModule
from app.modules.system.test_module import SystemTestModule
from app.modules.system.text_input_module import SystemTextInputModule
from app.modules.system.volume_module import SystemVolumeModule
from app.modules.system.window_control_module import SystemWindowControlModule
from app.settings.trigger_store import TriggerStore


MAX_AI_ACTIONS_PER_FEATURE = 64


class ModuleRegistry:
    def __init__(self, trigger_store: TriggerStore | None = None) -> None:
        self._modules: list[AssistantModule] = []
        self.trigger_store = trigger_store

    def register(self, module: AssistantModule) -> None:
        if self.trigger_store is not None:
            module.set_trigger_store(self.trigger_store)
        self._modules.append(module)

    def all(self) -> list[AssistantModule]:
        return list(self._modules)

    def get_module_by_feature_id(self, feature_id: str) -> AssistantModule | None:
        for module in self._modules:
            if module.feature_id == feature_id:
                return module
        return None

    def execute_action(
        self,
        feature_id: str,
        action_id: str,
        arguments: dict[str, Any] | None = None,
    ) -> tuple[AssistantModule, ModuleResponse] | None:
        module = self.get_module_by_feature_id(feature_id)
        if module is None:
            return None
        if action_id not in module.get_default_trigger_groups():
            return None
        response = module.execute_action(action_id, arguments or {})
        if response is None:
            return None
        return module, response

    def get_feature_trigger_data(self) -> list[dict]:
        return [self.build_feature_trigger_response(module) for module in self._modules]

    def get_feature_trigger_defaults(self) -> list[dict]:
        return [
            {
                "feature_id": module.feature_id,
                "display_name": module.display_name,
                "plan": self._plan_value(module),
                "triggers": self._flatten_groups(module.get_default_trigger_groups()),
                "default_trigger_groups": self._format_groups(
                    module,
                    module.get_default_trigger_groups(),
                ),
            }
            for module in self._modules
        ]

    def get_ai_capabilities(self) -> list[dict]:
        result: list[dict] = []
        for module in self._modules:
            supports_structured = (
                module.__class__.execute_action is not AssistantModule.execute_action
            )
            if not supports_structured:
                continue

            actions = []
            defaults = module.get_default_trigger_groups()
            for action_id, group in defaults.items():
                # Some local trigger groups are intentionally Snake-only. A
                # scalable semantic action can represent them more compactly.
                if group.get("melissa_semantic", True) is False:
                    continue

                argument_hint = str(group.get("argument_hint", "")).strip()
                trigger_examples = [
                    " ".join(trigger.split())
                    for trigger in group.get("triggers", [])
                    if isinstance(trigger, str) and trigger.strip()
                ][:4]
                if trigger_examples:
                    examples = "; ".join(trigger_examples)
                    argument_hint = (
                        f"{argument_hint} Голосовые примеры: {examples}."
                        if argument_hint
                        else f"Голосовые примеры: {examples}."
                    )

                actions.append({
                    "action_id": action_id,
                    "display_name": str(group.get("display_name", action_id)),
                    "argument_hint": argument_hint[:320],
                })

            if actions:
                result.append({
                    "feature_id": module.feature_id,
                    "display_name": module.display_name,
                    "actions": actions[:MAX_AI_ACTIONS_PER_FEATURE],
                })

        return result

    def get_public_capabilities(self) -> list[dict]:
        return [
            {
                "feature_id": module.feature_id,
                "display_name": module.display_name,
                "plan": self._plan_value(module),
                "actions": self._format_groups(module, module.get_trigger_groups()),
            }
            for module in self._modules
            if module.feature_id != "system.test"
        ]

    def build_feature_trigger_response(self, module: AssistantModule) -> dict:
        trigger_groups = module.get_trigger_groups()
        return {
            "feature_id": module.feature_id,
            "display_name": module.display_name,
            "plan": self._plan_value(module),
            "triggers": module.get_triggers(),
            "trigger_groups": self._format_groups(module, trigger_groups),
        }

    def _format_groups(
        self,
        module: AssistantModule,
        groups: dict[str, dict],
    ) -> list[dict]:
        defaults = module.get_default_trigger_groups()
        structured = module.__class__.execute_action is not AssistantModule.execute_action
        return [
            {
                "action_id": action_id,
                "display_name": str(group.get("display_name", action_id)),
                "triggers": list(group.get("triggers", [])),
                "argument_hint": str(
                    defaults.get(action_id, {}).get("argument_hint", "")
                ),
                "melissa_semantic": structured
                and defaults.get(action_id, {}).get("melissa_semantic", True) is not False,
                "snake_triggers": defaults.get(action_id, {}).get("snake_triggers", True) is not False,
            }
            for action_id, group in groups.items()
        ]

    def _flatten_groups(self, groups: dict[str, dict]) -> list[str]:
        triggers: list[str] = []
        seen: set[str] = set()
        for group in groups.values():
            for trigger in group.get("triggers", []):
                if not isinstance(trigger, str) or trigger in seen:
                    continue
                triggers.append(trigger)
                seen.add(trigger)
        return triggers

    def _plan_value(self, module: AssistantModule) -> str:
        return module.plan.value if hasattr(module.plan, "value") else str(module.plan)


def create_default_registry(trigger_store: TriggerStore | None = None) -> ModuleRegistry:
    registry = ModuleRegistry(trigger_store=trigger_store)
    registry.register(SystemTestModule())

    if os.environ.get(DESKTOP_TOKEN_ENV):
        registry.register(SystemSocialMessagingModule())

    registry.register(SystemPowerControlModule())
    registry.register(SystemSchedulerModule())
    registry.register(SystemScreenRecordingModule())
    registry.register(SystemMonitorControlModule())
    registry.register(SystemBrightnessModule())
    registry.register(SystemStatusModule())
    registry.register(SystemScreenshotModule())
    registry.register(SystemBrowserControlModule())
    registry.register(SystemTextInputModule())
    registry.register(SystemClipboardModule())
    registry.register(SystemKeyboardModule())
    registry.register(SystemFileNavigationModule())
    registry.register(SystemVolumeModule())
    registry.register(SystemMediaControlModule())
    registry.register(SystemWindowControlModule())
    registry.register(SystemAppLauncherModule())
    return registry
