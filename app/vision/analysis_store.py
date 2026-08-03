from __future__ import annotations

import re
import time
from threading import Lock, Timer
from typing import Any, Callable
from uuid import uuid4

from app.vision.screen_capture import CapturedScreen


MAX_ANNOTATIONS = 8
MAX_ACTIVE_ANALYSES = 4
ANALYSIS_TTL_SECONDS = 5 * 60
ACTION_TTL_SECONDS = 90
RISKY_ACTION_MARKERS = (
    "удал",
    "стер",
    "оплат",
    "купить",
    "покуп",
    "отправ",
    "опубликов",
    "разместить",
    "парол",
    "разрешени",
    "установ",
    "деинсталл",
    "форматир",
    "сброс",
    "безопасност",
    "delete",
    "remove",
    "payment",
    "pay",
    "buy",
    "purchase",
    "send",
    "publish",
    "password",
    "permission",
    "install",
    "uninstall",
    "format",
    "reset",
)


def _clean_text(value: object, limit: int) -> str:
    safe = re.sub(r"[\x00-\x1f\x7f]", " ", str(value or ""))
    return " ".join(safe.split())[:limit].strip()


def _normalized_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if number < 0 or number > 1:
        return None

    return number


def _contains_risky_action(value: object) -> bool:
    normalized = _clean_text(value, 1000).casefold()
    return any(marker in normalized for marker in RISKY_ACTION_MARKERS)


class ScreenAnalysisStore:
    """Keeps sensitive screenshots only in short-lived local memory."""

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._clock = clock
        self._lock = Lock()
        self._items: dict[str, dict[str, Any]] = {}
        self._expiry_timers: dict[str, Timer] = {}

    def _drop_locked(self, analysis_id: str) -> None:
        self._items.pop(analysis_id, None)
        timer = self._expiry_timers.pop(analysis_id, None)
        if timer is not None:
            timer.cancel()

    def _expire(self, analysis_id: str) -> None:
        with self._lock:
            self._items.pop(analysis_id, None)
            self._expiry_timers.pop(analysis_id, None)

    def _prune_locked(self, now: float) -> None:
        expired = [
            analysis_id
            for analysis_id, item in self._items.items()
            if now - float(item["created_at_monotonic"])
            > ANALYSIS_TTL_SECONDS
        ]
        for analysis_id in expired:
            self._drop_locked(analysis_id)

    @staticmethod
    def _normalize_annotations(value: object) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []

        annotations: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        allowed_kinds = {"target", "step", "text", "warning"}

        for raw in value[:MAX_ANNOTATIONS]:
            if not isinstance(raw, dict):
                continue

            annotation_id = _clean_text(raw.get("id"), 40)
            label = _clean_text(raw.get("label"), 100)
            kind = _clean_text(raw.get("kind"), 20).lower()
            x = _normalized_number(raw.get("x"))
            y = _normalized_number(raw.get("y"))
            width = _normalized_number(raw.get("width"))
            height = _normalized_number(raw.get("height"))

            if (
                not annotation_id
                or annotation_id in seen_ids
                or not label
                or kind not in allowed_kinds
                or x is None
                or y is None
                or width is None
                or height is None
            ):
                continue

            width = min(width, 1 - x)
            height = min(height, 1 - y)
            if width < 0.005 or height < 0.005:
                continue

            try:
                step = max(0, min(8, int(raw.get("step", 0))))
            except (TypeError, ValueError):
                step = 0

            seen_ids.add(annotation_id)
            annotations.append({
                "id": annotation_id,
                "label": label,
                "kind": kind,
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "step": step,
            })

        return annotations

    def create(
        self,
        capture: CapturedScreen,
        plan: dict[str, Any],
        click_was_requested: bool,
    ) -> dict[str, Any]:
        now = self._clock()
        analysis_id = uuid4().hex
        annotations = self._normalize_annotations(plan.get("annotations"))
        annotation_by_id = {
            annotation["id"]: annotation
            for annotation in annotations
        }
        raw_action = plan.get("action")
        action = {
            "type": "none",
            "available": False,
            "requested": click_was_requested,
            "label": "",
            "risk": "blocked",
            "reason": (
                "Безопасное нажатие не предложено."
                if click_was_requested
                else "Нажатие не запрошено."
            ),
        }
        internal_action = None

        if isinstance(raw_action, dict):
            target_id = _clean_text(raw_action.get("target_id"), 40)
            label = _clean_text(raw_action.get("label"), 100)
            reason = _clean_text(raw_action.get("reason"), 240)
            target = annotation_by_id.get(target_id)
            target_label = (
                str(target.get("label", ""))
                if isinstance(target, dict)
                else ""
            )
            risky = _contains_risky_action(
                f"{label} {target_label} {reason}",
            )
            can_click = (
                click_was_requested
                and raw_action.get("type") == "click"
                and raw_action.get("risk") == "safe"
                and target is not None
                and target.get("kind") in {"target", "step"}
                and capture.foreground_window is not None
                and not risky
            )

            if can_click and target is not None:
                center_x = target["x"] + target["width"] / 2
                center_y = target["y"] + target["height"] / 2
                action = {
                    "type": "click",
                    "available": True,
                    "requested": True,
                    "label": label or target["label"],
                    "risk": "safe",
                    "reason": reason or "Одно обратимое нажатие.",
                    "expires_in_seconds": ACTION_TTL_SECONDS,
                }
                internal_action = {
                    "x": center_x,
                    "y": center_y,
                    "label": action["label"],
                    "created_at_monotonic": now,
                    "foreground_window": capture.foreground_window,
                    "used": False,
                }
            elif raw_action.get("risk") == "blocked" or risky:
                action = {
                    "type": "none",
                    "available": False,
                    "requested": click_was_requested,
                    "label": label,
                    "risk": "blocked",
                    "reason": (
                        reason
                        or "Это действие нельзя выполнять автоматически."
                    ),
                }
            elif click_was_requested and raw_action.get("type") == "click":
                action = {
                    "type": "none",
                    "available": False,
                    "requested": True,
                    "label": label or target_label,
                    "risk": "blocked",
                    "reason": (
                        "Не удалось безопасно закрепить действие за активным "
                        "окном. Покажу цель рамкой, но нажимать не буду."
                    ),
                }

        public = {
            "id": analysis_id,
            "answer": _clean_text(plan.get("answer"), 5000),
            "mode": (
                plan.get("mode")
                if plan.get("mode")
                in {"explain", "translate", "guide", "annotate"}
                else "explain"
            ),
            "annotations": annotations,
            "action": action,
            "canvas_available": True,
            "capture": {
                "width": capture.width,
                "height": capture.height,
                "one_shot": True,
            },
        }
        item = {
            "created_at_monotonic": now,
            "public": public,
            "image_data_url": capture.data_url,
            "action": internal_action,
            "canvas_drawing_id": None,
        }

        with self._lock:
            self._prune_locked(now)
            while len(self._items) >= MAX_ACTIVE_ANALYSES:
                oldest_id = min(
                    self._items,
                    key=lambda item_id: float(
                        self._items[item_id]["created_at_monotonic"],
                    ),
                )
                self._drop_locked(oldest_id)
            self._items[analysis_id] = item
            expiry_timer = Timer(
                ANALYSIS_TTL_SECONDS,
                self._expire,
                args=(analysis_id,),
            )
            expiry_timer.daemon = True
            self._expiry_timers[analysis_id] = expiry_timer
            expiry_timer.start()

        return public

    def get_canvas_source(self, analysis_id: str) -> dict[str, Any]:
        now = self._clock()
        with self._lock:
            self._prune_locked(now)
            item = self._items.get(str(analysis_id or ""))
            if item is None:
                raise KeyError("Screen analysis expired")
            drawing_id = item.get("canvas_drawing_id")
            if drawing_id:
                return {
                    "drawing_id": str(drawing_id),
                    "analysis": dict(item["public"]),
                }

            image_data_url = item.get("image_data_url")
            if not isinstance(image_data_url, str) or not image_data_url:
                raise KeyError("Screen source is no longer available")
            return {
                "image_data_url": image_data_url,
                "analysis": dict(item["public"]),
            }

    def mark_canvas_saved(
        self,
        analysis_id: str,
        drawing_id: str,
    ) -> None:
        with self._lock:
            item = self._items.get(str(analysis_id or ""))
            if item is None:
                raise KeyError("Screen analysis expired")
            item["canvas_drawing_id"] = str(drawing_id)
            item["image_data_url"] = None

    def take_confirmed_click(self, analysis_id: str) -> dict[str, Any]:
        now = self._clock()
        with self._lock:
            self._prune_locked(now)
            item = self._items.get(str(analysis_id or ""))
            if item is None:
                raise KeyError("Screen analysis expired")

            action = item.get("action")
            if not isinstance(action, dict) or action.get("used"):
                raise ValueError("No pending click")

            if (
                now - float(action["created_at_monotonic"])
                > ACTION_TTL_SECONDS
            ):
                action["used"] = True
                raise TimeoutError("Click confirmation expired")

            action["used"] = True
            confirmed = {
                "x": float(action["x"]),
                "y": float(action["y"]),
                "label": str(action["label"]),
                "foreground_window": action.get("foreground_window"),
            }
            self._drop_locked(str(analysis_id or ""))
            return confirmed

    def dismiss(self, analysis_id: str) -> None:
        with self._lock:
            self._drop_locked(str(analysis_id or ""))
