from app.features.plans import Plan
from app.modules.base import AssistantModule, ModuleResponse


class SystemTestModule(AssistantModule):
    feature_id = "system.test"
    display_name = "Тест модульной системы"
    plan = Plan.FREE
    default_triggers = [
        "проверка команды",
        "тест команды",
        "проверить команду",
    ]

    def can_handle(self, text: str) -> bool:
        return text.strip().lower() in self.get_triggers()

    def handle(self, text: str) -> ModuleResponse:
        return ModuleResponse(text="Модульная система работает.")
