from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.api.command_route_client import CommandRouteClient
from app.core.log_bus import add_log
from app.features.feature_gate import FeatureGate
from app.modules.base import AssistantModule, ModuleResponse
from app.settings.companion_store import CompanionSettingsStore

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
        settings_store: CompanionSettingsStore | None = None,
        semantic_client: CommandRouteClient | None = None,
    ) -> None:
        self.registry = registry
        self.feature_gate = feature_gate
        self.settings_store = settings_store or CompanionSettingsStore()
        self._semantic_client = semantic_client

    def route(self, text: str) -> CommandRouteResult | None:
        """Snake route: local trigger matching only, no neural network."""
        if not self.settings_store.get()["snake_command_mode_enabled"]:
            add_log("Змея отключена в настройках", meta={"text": text})
            return None

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
        """Melissa route: fast exact trigger first, then semantic action selection."""
        if not self.settings_store.get()["melissa_command_mode_enabled"]:
            return None

        command_text = text.strip().lower()

        # Fast path: exact known trigger. This saves latency for common commands.
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

        return self._route_semantic(command_text)

    def _route_semantic(self, command_text: str) -> CommandRouteResult | None:
        capabilities = self.registry.get_ai_capabilities()
        if not capabilities:
            return None

        try:
            if self._semantic_client is None:
                self._semantic_client = CommandRouteClient()
            result = self._semantic_client.resolve(command_text, capabilities)
        except Exception as error:
            add_log(
                "Semantic command routing недоступен",
                level="warn",
                meta={"error": str(error)},
            )
            return None

        if not result.matched:
            add_log(
                "Мелисса не выбрала локальную функцию",
                meta={"confidence": result.confidence, "reason": result.reason},
            )
            return None

        executed = self.registry.execute_action(
            result.feature_id,
            result.action_id,
            result.arguments,
        )
        if executed is None:
            add_log(
                "Semantic action отклонён локальным ядром",
                level="warn",
                meta={
                    "feature_id": result.feature_id,
                    "action_id": result.action_id,
                },
            )
            return None

        module, response = executed
        if not self.feature_gate.is_allowed(module.feature_id, module.plan):
            return None

        add_log(
            "Мелисса выбрала локальную функцию",
            meta={
                "feature_id": result.feature_id,
                "action_id": result.action_id,
                "confidence": result.confidence,
            },
        )
        return CommandRouteResult(module=module, response=response)
