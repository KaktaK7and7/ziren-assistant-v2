from app.features.plans import Plan
from app.modules.base import AssistantModule, ModuleResponse


class SystemTestModule(AssistantModule):
    feature_id = "system.test"
    plan = Plan.FREE

    _commands = {
        "проверка команды",
        "тест команды",
        "проверить команду",
    }

    def can_handle(self, text: str) -> bool:
        return text.strip().lower() in self._commands

    def handle(self, text: str) -> ModuleResponse:
        return ModuleResponse(text="Модульная система работает.")
