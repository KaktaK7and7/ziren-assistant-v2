from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.features.plans import Plan


@dataclass(frozen=True)
class ModuleResponse:
    text: str


class AssistantModule(ABC):
    feature_id: str
    plan: Plan = Plan.FREE

    @abstractmethod
    def can_handle(self, text: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def handle(self, text: str) -> ModuleResponse:
        raise NotImplementedError
