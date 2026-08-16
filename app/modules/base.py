from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

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
    default_trigger_groups: dict[str, dict[str, Any]] = {}
    trigger_store: TriggerStore | None = None

    def set_trigger_store(self, trigger_store: TriggerStore) -> None:
        self.trigger_store = trigger_store

    def get_trigger_groups(self) -> dict[str, dict[str, Any]]:
        default_groups = self.get_default_trigger_groups()

        if self.trigger_store is not None:
            return self.trigger_store.get_groups(self.feature_id, default_groups)

        return {
            action_id: {
                "display_name": str(group.get("display_name", action_id)),
                "triggers": list(group.get("triggers", [])),
            }
            for action_id, group in default_groups.items()
        }

    def get_triggers(self) -> list[str]:
        trigger_groups = self.get_trigger_groups()
        triggers: list[str] = []
        seen: set[str] = set()

        for group in trigger_groups.values():
            for trigger in group.get("triggers", []):
                if not isinstance(trigger, str) or trigger in seen:
                    continue

                triggers.append(trigger)
                seen.add(trigger)

        if triggers:
            return triggers

        if self.trigger_store is not None:
            return self.trigger_store.get(self.feature_id, self.default_triggers)

        return list(self.default_triggers)

    def get_default_trigger_groups(self) -> dict[str, dict[str, Any]]:
        if self.default_trigger_groups:
            return {
                action_id: {
                    "display_name": str(group.get("display_name", action_id)),
                    "triggers": list(group.get("triggers", [])),
                    "argument_hint": str(group.get("argument_hint", "")),
                }
                for action_id, group in self.default_trigger_groups.items()
                if isinstance(action_id, str) and isinstance(group, dict)
            }

        if self.default_triggers:
            return {
                "default": {
                    "display_name": self.display_name,
                    "triggers": list(self.default_triggers),
                    "argument_hint": "",
                }
            }

        return {}

    def get_action_triggers(self, action_id: str) -> list[str]:
        group = self.get_trigger_groups().get(action_id)

        if not isinstance(group, dict):
            return []

        triggers = group.get("triggers", [])

        if not isinstance(triggers, list):
            return []

        return [trigger for trigger in triggers if isinstance(trigger, str)]

    def get_action_argument_hint(self, action_id: str) -> str:
        group = self.get_default_trigger_groups().get(action_id, {})
        return str(group.get("argument_hint", ""))

    def execute_action(
        self,
        action_id: str,
        arguments: dict[str, Any] | None = None,
    ) -> ModuleResponse | None:
        """Execute an allow-listed structured action selected by Melissa.

        Modules opt in action-by-action. Returning None means the action is not
        available for semantic execution and must never be guessed by the router.
        """
        return None

    @abstractmethod
    def can_handle(self, text: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def handle(self, text: str) -> ModuleResponse:
        raise NotImplementedError
