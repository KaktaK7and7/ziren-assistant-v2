from app.modules.base import AssistantModule
from app.modules.system.test_module import SystemTestModule
from app.modules.system.volume_module import SystemVolumeModule


class ModuleRegistry:
    def __init__(self) -> None:
        self._modules: list[AssistantModule] = []

    def register(self, module: AssistantModule) -> None:
        self._modules.append(module)

    def all(self) -> list[AssistantModule]:
        return list(self._modules)

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


def create_default_registry() -> ModuleRegistry:
    registry = ModuleRegistry()
    registry.register(SystemTestModule())
    registry.register(SystemVolumeModule())
    return registry
