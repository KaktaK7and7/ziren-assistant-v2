from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from app.api.desktop_auth import (
    DesktopAuthenticationError,
    desktop_authorization_headers,
    normalize_desktop_token,
)
from app.config.settings import AUTH_SITE_URL, DESKTOP_TOKEN_ENV, get_desktop_token


@dataclass(frozen=True)
class SemanticCommandResult:
    matched: bool = False
    feature_id: str = ""
    action_id: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    reason: str = ""


class CommandRouteClient:
    def __init__(
        self,
        desktop_token: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        token = normalize_desktop_token(desktop_token or get_desktop_token())
        try:
            self.headers = desktop_authorization_headers(token)
        except DesktopAuthenticationError as error:
            raise RuntimeError(f"{error} ({DESKTOP_TOKEN_ENV})") from error

        self.client = client or httpx.Client(
            base_url=AUTH_SITE_URL,
            timeout=14.0,
        )

    def resolve(
        self,
        message: str,
        capabilities: list[dict],
    ) -> SemanticCommandResult:
        text = str(message or "").strip()
        if not text or not capabilities:
            return SemanticCommandResult()

        response = self.client.post(
            "/api/assistant/command-route",
            headers=self.headers,
            json={
                "message": text[:2000],
                "capabilities": capabilities[:80],
            },
        )

        if response.status_code in (401, 403):
            return SemanticCommandResult(reason="authentication required")

        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict) or data.get("matched") is not True:
            return SemanticCommandResult(
                confidence=_safe_confidence(data.get("confidence") if isinstance(data, dict) else 0),
                reason=str(data.get("reason") or "")[:300] if isinstance(data, dict) else "",
            )

        confidence = _safe_confidence(data.get("confidence"))
        if confidence < 0.78:
            return SemanticCommandResult(
                confidence=confidence,
                reason="semantic confidence below threshold",
            )

        arguments = data.get("arguments")
        return SemanticCommandResult(
            matched=True,
            feature_id=str(data.get("feature_id") or "")[:100],
            action_id=str(data.get("action_id") or "")[:120],
            arguments=arguments if isinstance(arguments, dict) else {},
            confidence=confidence,
            reason=str(data.get("reason") or "")[:300],
        )


def _safe_confidence(value: object) -> float:
    if isinstance(value, bool):
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))
