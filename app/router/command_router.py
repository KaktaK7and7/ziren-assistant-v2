from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.features.feature_gate import FeatureGate
from app.modules.base import AssistantModule, ModuleResponse

if TYPE_CHECKING:
    from app.modules.registry import ModuleRegistry


@dataclass(frozen=True)
class CommandRouteResult:
    module: AssistantModule
    response: ModuleResponse


class CommandRouter:
    def __init__(
        self,
        registry: "ModuleRegistry",
        feature_gate: FeatureGate,
    ) -> None:
        self.registry = registry
        self.feature_gate = feature_gate

    def route(self, text: str) -> CommandRouteResult | None:
        command_text = text.strip().lower()

        for module in self.registry.all():
            if not module.can_handle(command_text):
                continue

            if not self.feature_gate.is_allowed(module.feature_id, module.plan):
                return None

            return CommandRouteResult(
                module=module,
                response=module.handle(command_text),
            )

        return None

    def route_explicit(self, text: str) -> CommandRouteResult | None:
        command_text = text.strip().lower()

        for module in self.registry.all():
            has_explicit_trigger = any(
                command_text == trigger.strip().lower()
                or command_text.startswith(f"{trigger.strip().lower()} ")
                for trigger in module.get_triggers()
                if trigger.strip()
            )

            if not has_explicit_trigger or not module.can_handle(command_text):
                continue

            if not self.feature_gate.is_allowed(module.feature_id, module.plan):
                return None

            return CommandRouteResult(
                module=module,
                response=module.handle(command_text),
            )

        return None
