from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.features.plans import Plan
from app.settings.trigger_store import TriggerStore


@dataclass(frozen=True)
class ModuleResponse:
    text: str


class AssistantModule(ABC):
    feature_id: str
    display_name: str = "Без названия"
    plan: Plan = Plan.FREE
    default_triggers: list[str] = []
    trigger_store: TriggerStore | None = None

    def set_trigger_store(self, trigger_store: TriggerStore) -> None:
        self.trigger_store = trigger_store

    def get_triggers(self) -> list[str]:
        if self.trigger_store is not None:
            return self.trigger_store.get(self.feature_id, self.default_triggers)

        return list(self.default_triggers)

    @abstractmethod
    def can_handle(self, text: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def handle(self, text: str) -> ModuleResponse:
        raise NotImplementedError
