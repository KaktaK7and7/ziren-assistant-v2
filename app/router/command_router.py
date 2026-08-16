from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.api.command_route_client import CommandRouteClient
from app.core.log_bus import add_log
from app.features.feature_gate import FeatureGate
from app.features.plans import Plan
from app.modules.base import AssistantModule, ModuleResponse
from app.settings.companion_store import CompanionSettingsStore

if TYPE_CHECKING:
    from app.modules.registry import ModuleRegistry


class _RoutingNoticeModule(AssistantModule):
    """Non-executing module used to keep failed command intent out of AI chat."""

    feature_id = "system.command_router"
    display_name = "Маршрутизация команд"
    plan = Plan.FREE

    def can_handle(self, text: str) -> bool:
        return False

    def handle(self, text: str) -> ModuleResponse:
        return ModuleResponse(text="Команда не выполнена.")


_ROUTING_NOTICE_MODULE = _RoutingNoticeModule()


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
        """Melissa route: semantic selection first, local fallback only on outage."""
        if not self.settings_store.get()["melissa_command_mode_enabled"]:
            return None

        command_text = text.strip().lower()
        if not command_text:
            return None

        capability_builder = getattr(self.registry, "get_ai_capabilities", None)
        capabilities = capability_builder() if callable(capability_builder) else []
        if not capabilities:
            return self._route_explicit_local_fallback(command_text)

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
            return self._route_explicit_local_fallback(command_text)

        if result.matched:
            module = self.registry.get_module_by_feature_id(result.feature_id)
            if module is None:
                return self._command_rejected_notice(
                    result.reason,
                    result.confidence,
                    "Не нашла такую локальную функцию в этой версии Ziren.",
                )
            if not self.feature_gate.is_allowed(module.feature_id, module.plan):
                return self._command_rejected_notice(
                    result.reason,
                    result.confidence,
                    "Эта функция сейчас недоступна для твоего тарифа.",
                )

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
                return self._command_rejected_notice(
                    result.reason,
                    result.confidence,
                    "Поняла команду, но эта операция ещё не подключена к локальному ядру.",
                )

            module, response = executed
            add_log(
                "Мелисса выбрала локальную функцию",
                meta={
                    "feature_id": result.feature_id,
                    "action_id": result.action_id,
                    "confidence": result.confidence,
                },
            )
            return CommandRouteResult(module=module, response=response)

        if result.command_like:
            add_log(
                "Мелисса распознала команду, но не выбрала безопасное действие",
                level="warn",
                meta={
                    "confidence": result.confidence,
                    "reason": result.reason,
                },
            )
            return self._command_rejected_notice(
                result.reason,
                result.confidence,
                (
                    "Поняла, что ты хочешь выполнить команду, но не нашла "
                    "достаточно уверенного безопасного действия. Скажи чуть точнее."
                ),
            )

        if result.reason.startswith("system:"):
            add_log(
                "Semantic selector недоступен, использую локальный fallback",
                level="warn",
                meta={"reason": result.reason},
            )
            return self._route_explicit_local_fallback(command_text)

        add_log(
            "Мелисса определила обычный разговор",
            meta={"reason": result.reason},
        )
        return None

    def _route_explicit_local_fallback(
        self,
        command_text: str,
    ) -> CommandRouteResult | None:
        """Safe outage fallback for already-known exact triggers only."""
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

            add_log(
                "Мелисса использует локальный trigger fallback",
                level="warn",
                meta={"feature_id": module.feature_id},
            )
            return CommandRouteResult(
                module=module,
                response=module.handle(command_text),
            )

        return None

    def _command_rejected_notice(
        self,
        reason: str,
        confidence: float,
        text: str,
    ) -> CommandRouteResult:
        add_log(
            "Команда Мелиссы не выполнена",
            level="warn",
            meta={"confidence": confidence, "reason": reason},
        )
        return CommandRouteResult(
            module=_ROUTING_NOTICE_MODULE,
            response=ModuleResponse(text=text),
        )
