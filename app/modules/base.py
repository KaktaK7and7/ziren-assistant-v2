from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.features.plans import Plan


@dataclass(frozen=True)
class ModuleResponse:
    text: str


class AssistantModule(ABC):
    feature_id: str
    display_name: str = "Без названия"
    plan: Plan = Plan.FREE
    default_triggers: list[str] = []

    def get_triggers(self) -> list[str]:
        return self.default_triggers

    @abstractmethod
    def can_handle(self, text: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def handle(self, text: str) -> ModuleResponse:
        raise NotImplementedError
