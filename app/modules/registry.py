from app.modules.base import AssistantModule
from app.modules.system.app_launcher_module import SystemAppLauncherModule
from app.modules.system.media_control_module import SystemMediaControlModule
from app.modules.system.test_module import SystemTestModule
from app.modules.system.volume_module import SystemVolumeModule
from app.modules.system.window_control_module import SystemWindowControlModule
from app.settings.trigger_store import TriggerStore


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
                    module.get_default_trigger_groups()
                ),
            }
            for module in self._modules
        ]

    def get_ai_capabilities(self) -> list[dict]:
        module_capabilities = [
            {
                "feature_id": module.feature_id,
                "display_name": module.display_name,
                "actions": [
                    str(group.get("display_name", action_id))
                    for action_id, group in module.get_trigger_groups().items()
                ][:16],
            }
            for module in self._modules
        ]

        return [
            *module_capabilities,
            {
                "feature_id": "screen.analysis",
                "display_name": "Разовый анализ экрана",
                "actions": [
                    "Сделать снимок основного экрана только по явной просьбе",
                    "Объяснить видимые элементы и предложить следующие шаги",
                ],
            },
        ]

    def build_feature_trigger_response(self, module: AssistantModule) -> dict:
        trigger_groups = module.get_trigger_groups()

        return {
            "feature_id": module.feature_id,
            "display_name": module.display_name,
            "plan": self._plan_value(module),
            "triggers": module.get_triggers(),
            "trigger_groups": self._format_groups(trigger_groups),
        }

    def _format_groups(self, groups: dict[str, dict]) -> list[dict]:
        return [
            {
                "action_id": action_id,
                "display_name": str(group.get("display_name", action_id)),
                "triggers": list(group.get("triggers", [])),
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
    registry.register(SystemVolumeModule())
    registry.register(SystemMediaControlModule())
    registry.register(SystemWindowControlModule())
    registry.register(SystemAppLauncherModule())
    return registry
