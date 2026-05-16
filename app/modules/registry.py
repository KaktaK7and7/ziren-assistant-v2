from app.modules.base import AssistantModule
from app.modules.system.test_module import SystemTestModule


class ModuleRegistry:
    def __init__(self) -> None:
        self._modules: list[AssistantModule] = []

    def register(self, module: AssistantModule) -> None:
        self._modules.append(module)

    def all(self) -> list[AssistantModule]:
        return list(self._modules)


def create_default_registry() -> ModuleRegistry:
    registry = ModuleRegistry()
    registry.register(SystemTestModule())
    return registry
