import os
from dataclasses import dataclass

import httpx

from app.app_launcher.debug import app_debug_step
from app.app_launcher.models import AppTarget
from app.config.settings import AI_SERVICE_URL


@dataclass
class AIDisambiguationResult:
    selected_index: int | None
    confidence: float
    spoken_name: str | None = None
    reason: str = ""


class AppAIDisambiguator:
    MIN_CONFIDENCE = 0.82
    MAX_CANDIDATES = 40

    def __init__(self, ai_service_url: str = AI_SERVICE_URL, timeout: float = 8.0) -> None:
        self.client = httpx.Client(base_url=ai_service_url, timeout=timeout)

    def choose(
        self,
        query: str,
        candidates: list[AppTarget],
    ) -> AIDisambiguationResult:
        if not candidates:
            return AIDisambiguationResult(selected_index=None, confidence=0.0)

        limited_candidates = candidates[: self.MAX_CANDIDATES]
        request_payload = {
            "query": query,
            "candidates": [
                self._candidate_payload(index, target)
                for index, target in enumerate(limited_candidates, start=1)
            ],
        }
        index_to_local_position = {
            index: local_position
            for local_position, index in enumerate(range(1, len(limited_candidates) + 1))
        }

        try:
            app_debug_step(
                "ai request",
                {
                    "url": f"{AI_SERVICE_URL}/app-launcher/resolve",
                    "query": query,
                    "candidates_count": len(limited_candidates),
                    "candidate_names": [
                        candidate.name for candidate in limited_candidates[:20]
                    ],
                    "payload": request_payload,
                },
            )
            response = self.client.post(
                "/app-launcher/resolve",
                json=request_payload,
            )
            app_debug_step(
                "ai raw response",
                {
                    "status_code": response.status_code,
                    "text_preview": response.text[:500],
                },
            )
            response.raise_for_status()
            payload = response.json()
            selected_index = payload.get("selected_index")
            confidence = float(payload.get("confidence", 0.0) or 0.0)
            spoken_name = payload.get("spoken_name")
            reason = str(payload.get("reason", ""))

            if spoken_name is not None:
                spoken_name = str(spoken_name).strip() or None

            app_debug_step(
                "ai parsed response",
                {
                    "selected_index": selected_index,
                    "confidence": confidence,
                    "spoken_name": spoken_name,
                    "reason": reason,
                },
            )

            if (
                selected_index is None
                or confidence < self.MIN_CONFIDENCE
                or int(selected_index) not in index_to_local_position
            ):
                app_debug_step(
                    "ai selection rejected",
                    {
                        "selected_index": selected_index,
                        "confidence": confidence,
                        "reason": reason,
                    },
                )
                return AIDisambiguationResult(
                    selected_index=None,
                    confidence=confidence,
                    spoken_name=spoken_name,
                    reason=reason,
                )

            return AIDisambiguationResult(
                selected_index=index_to_local_position[int(selected_index)],
                confidence=confidence,
                spoken_name=spoken_name,
                reason=reason,
            )
        except Exception as error:
            app_debug_step(
                "ai request failed",
                {
                    "error": str(error),
                },
            )
            return AIDisambiguationResult(
                selected_index=None,
                confidence=0.0,
                reason=str(error),
            )

    def _candidate_payload(self, index: int, target: AppTarget) -> dict:
        return {
            "index": index,
            "target_id": target.target_id,
            "name": target.name,
            "type": target.type,
            "source": target.source,
            "aliases": target.aliases[:10],
            "appid": target.appid or "",
            "path_basename": os.path.basename(target.path) if target.path else "",
        }
