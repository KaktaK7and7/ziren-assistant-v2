import re
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
        module = self._select_local_module(command_text)
        if module is None:
            return None

        if not self.feature_gate.is_allowed(module.feature_id, module.plan):
            return None

        return CommandRouteResult(
            module=module,
            response=module.handle(command_text),
        )

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

        if result.reason.startswith("subscription:"):
            parts = result.reason.split(":", 2)
            code = parts[1] if len(parts) > 1 else "subscription_required"
            server_message = parts[2] if len(parts) > 2 else ""
            add_log(
                "Мелисса ограничена тарифом",
                level="warn",
                meta={"code": code},
            )
            if code == "ai_budget_exhausted":
                notice_text = (
                    server_message
                    or "AI-ресурс на текущий период закончился. Змея и локальные команды продолжают работать."
                )
            else:
                notice_text = (
                    server_message
                    or "Мелисса доступна на тарифах Plus и Pro. Змея и локальные команды остаются бесплатными."
                )
            return self._command_rejected_notice(result.reason, 0.0, notice_text)

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
        """Safe outage fallback for already-known exact/prefix triggers only."""
        module = self._select_local_module(command_text, require_explicit_prefix=True)
        if module is None:
            return None

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

    def _select_local_module(
        self,
        command_text: str,
        *,
        require_explicit_prefix: bool = False,
    ) -> AssistantModule | None:
        """Pick the most specific local trigger instead of registry order.

        Many useful phrases intentionally overlap: app.launch owns "открой",
        while file navigation owns "открой загрузки"; social messaging owns
        "напиши", while text input owns "напиши здесь". First-match routing
        makes those pairs fragile. Longest exact/prefix trigger wins, while a
        module with stateful can_handle() (for example pending app selection)
        can still participate with score 0 in normal Snake mode.
        """
        best_module: AssistantModule | None = None
        best_score = -1

        for module in self.registry.all():
            if not module.can_handle(command_text):
                continue

            score = self._module_trigger_score(module, command_text)
            if require_explicit_prefix and score < 20_000:
                continue

            if score > best_score:
                best_module = module
                best_score = score

        return best_module

    @classmethod
    def _module_trigger_score(cls, module: AssistantModule, text: str) -> int:
        normalized = cls._normalize_trigger_text(text)
        best = 0

        for trigger in module.get_triggers():
            needle = cls._normalize_trigger_text(trigger)
            if not needle:
                continue

            length = len(needle)
            if normalized == needle:
                best = max(best, 30_000 + length)
                continue

            if normalized.startswith(f"{needle} "):
                best = max(best, 20_000 + length)
                continue

            if re.search(rf"\b{re.escape(needle)}\b", normalized):
                best = max(best, 10_000 + length)

        return best

    @staticmethod
    def _normalize_trigger_text(text: str) -> str:
        value = str(text or "").lower().replace("ё", "е")
        value = re.sub(r"[^\w\s]+", " ", value, flags=re.UNICODE)
        return re.sub(r"\s+", " ", value).strip()

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
