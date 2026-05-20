from app.modules.base import AssistantModule
from app.settings.trigger_store import TriggerStore
from app.modules.system.test_module import SystemTestModule
from app.modules.system.volume_module import SystemVolumeModule


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
        return [
            {
                "feature_id": module.feature_id,
                "display_name": module.display_name,
                "plan": module.plan.value if hasattr(module.plan, "value") else str(module.plan),
                "triggers": module.get_triggers(),
            }
            for module in self._modules
        ]

    def get_feature_trigger_defaults(self) -> list[dict]:
        return [
            {
                "feature_id": module.feature_id,
                "display_name": module.display_name,
                "plan": module.plan.value if hasattr(module.plan, "value") else str(module.plan),
                "default_triggers": list(module.default_triggers),
            }
            for module in self._modules
        ]


def create_default_registry(trigger_store: TriggerStore | None = None) -> ModuleRegistry:
    registry = ModuleRegistry(trigger_store=trigger_store)
    registry.register(SystemTestModule())
    registry.register(SystemVolumeModule())
    return registry
