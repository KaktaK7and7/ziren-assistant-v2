from __future__ import annotations

import os
import queue
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Iterable

from app.vision.screen_capture import CapturedScreen
from app.vision.windows_geometry import enable_per_monitor_dpi_awareness


MAX_UI_ELEMENTS = 700
MAX_UI_TREE_DEPTH = 14
UI_ENUMERATION_TIMEOUT_SECONDS = 1.6
GROUNDABLE_ANNOTATION_KINDS = {"target", "step"}
INTERACTIVE_CONTROL_TYPES = {
    "ButtonControl",
    "CheckBoxControl",
    "ComboBoxControl",
    "EditControl",
    "HyperlinkControl",
    "ListItemControl",
    "MenuItemControl",
    "RadioButtonControl",
    "SplitButtonControl",
    "TabItemControl",
    "TreeItemControl",
}
TOKEN_RE = re.compile(r"[0-9a-zа-яё_]+", re.IGNORECASE)


@dataclass(frozen=True)
class UiElement:
    name: str
    control_type: str
    x: float
    y: float
    width: float
    height: float
    automation_id: str = ""
    class_name: str = ""

    @property
    def center(self) -> tuple[float, float]:
        return (
            self.x + self.width / 2,
            self.y + self.height / 2,
        )


@dataclass(frozen=True)
class UiGroundingMatch:
    annotation_id: str
    annotation_label: str
    element_name: str
    control_type: str
    score: float


@dataclass
class _UiCollectionRequest:
    capture: CapturedScreen
    done: threading.Event = field(default_factory=threading.Event)
    elements: list[UiElement] = field(default_factory=list)


_ui_requests: queue.Queue[_UiCollectionRequest] = queue.Queue()
_ui_worker_lock = threading.Lock()
_ui_worker: threading.Thread | None = None


def _clean_text(value: object, limit: int = 180) -> str:
    safe = re.sub(r"[\x00-\x1f\x7f]", " ", str(value or ""))
    return " ".join(safe.split())[:limit].strip()


def _normalized_text(value: object) -> str:
    return " ".join(TOKEN_RE.findall(_clean_text(value).casefold()))


def _tokens(value: object) -> set[str]:
    return {
        token
        for token in TOKEN_RE.findall(_clean_text(value).casefold())
        if len(token) >= 2
    }


def _element_from_pixels(
    *,
    name: str,
    control_type: str,
    automation_id: str,
    class_name: str,
    left: int,
    top: int,
    right: int,
    bottom: int,
    screen_width: int,
    screen_height: int,
) -> UiElement | None:
    if screen_width <= 0 or screen_height <= 0:
        return None

    clipped_left = min(screen_width, max(0, int(left)))
    clipped_top = min(screen_height, max(0, int(top)))
    clipped_right = min(screen_width, max(0, int(right)))
    clipped_bottom = min(screen_height, max(0, int(bottom)))
    width = clipped_right - clipped_left
    height = clipped_bottom - clipped_top
    if width < 2 or height < 2:
        return None

    return UiElement(
        name=_clean_text(name),
        control_type=_clean_text(control_type, 80),
        automation_id=_clean_text(automation_id, 120),
        class_name=_clean_text(class_name, 120),
        x=clipped_left / screen_width,
        y=clipped_top / screen_height,
        width=width / screen_width,
        height=height / screen_height,
    )


def _collect_ui_elements_on_automation_thread(
    capture: CapturedScreen,
    automation: Any,
) -> list[UiElement]:
    screen_width = int(capture.source_width or capture.width)
    screen_height = int(capture.source_height or capture.height)
    deadline = time.monotonic() + UI_ENUMERATION_TIMEOUT_SECONDS
    elements: list[UiElement] = []
    seen: set[tuple[str, str, int, int, int, int]] = set()

    root = automation.ControlFromHandle(int(capture.foreground_window or 0))
    if root is None:
        return []

    controls: deque[tuple[Any, int]] = deque([(root, 0)])
    visited = 0
    while (
        controls
        and visited < MAX_UI_ELEMENTS
        and time.monotonic() < deadline
    ):
        control, depth = controls.popleft()
        visited += 1

        try:
            name = _clean_text(control.Name)
            offscreen = bool(control.IsOffscreen)
            rect = control.BoundingRectangle
            control_type = _clean_text(control.ControlTypeName, 80)
            automation_id = _clean_text(control.AutomationId, 120)
            class_name = _clean_text(control.ClassName, 120)
        except Exception:
            name = ""
            offscreen = True
            rect = None
            control_type = ""
            automation_id = ""
            class_name = ""

        if name and not offscreen and rect is not None:
            element = _element_from_pixels(
                name=name,
                control_type=control_type,
                automation_id=automation_id,
                class_name=class_name,
                left=rect.left,
                top=rect.top,
                right=rect.right,
                bottom=rect.bottom,
                screen_width=screen_width,
                screen_height=screen_height,
            )
            if element is not None:
                key = (
                    element.name.casefold(),
                    element.control_type,
                    round(element.x * screen_width),
                    round(element.y * screen_height),
                    round(element.width * screen_width),
                    round(element.height * screen_height),
                )
                if key not in seen:
                    seen.add(key)
                    elements.append(element)

        if depth >= MAX_UI_TREE_DEPTH:
            continue

        try:
            children = control.GetChildren()
        except Exception:
            children = []
        for child in children:
            controls.append((child, depth + 1))

    return elements


def _run_ui_worker() -> None:
    automation: Any | None = None
    initializer: Any | None = None

    while True:
        request = _ui_requests.get()
        try:
            if automation is None:
                import uiautomation as automation_module

                automation = automation_module
                initializer = automation.UIAutomationInitializerInThread()
            request.elements = _collect_ui_elements_on_automation_thread(
                request.capture,
                automation,
            )
        except Exception:
            request.elements = []
        finally:
            request.done.set()

        # Keep the initializer referenced for the whole lifetime of this
        # dedicated thread. UI Automation COM objects must never be reused on
        # a different thread.
        _ = initializer


def _ensure_ui_worker() -> None:
    global _ui_worker

    with _ui_worker_lock:
        if _ui_worker is not None and _ui_worker.is_alive():
            return
        _ui_worker = threading.Thread(
            target=_run_ui_worker,
            name="ziren-ui-grounding",
            daemon=True,
        )
        _ui_worker.start()


def collect_accessible_ui_elements(
    capture: CapturedScreen,
) -> list[UiElement]:
    """Read physical UI bounds from the analyzed Windows foreground window."""
    if os.name != "nt" or capture.foreground_window is None:
        return []

    enable_per_monitor_dpi_awareness()
    _ensure_ui_worker()
    request = _UiCollectionRequest(capture=capture)
    _ui_requests.put(request)
    if not request.done.wait(UI_ENUMERATION_TIMEOUT_SECONDS + 0.65):
        return []
    return list(request.elements)


def _lexical_score(query: str, element: UiElement) -> float | None:
    query_normalized = _normalized_text(query)
    query_tokens = _tokens(query)
    if not query_normalized or not query_tokens:
        return None

    best = 0.0
    for value in (element.name, element.automation_id):
        candidate_normalized = _normalized_text(value)
        candidate_tokens = _tokens(value)
        if not candidate_normalized or not candidate_tokens:
            continue

        score = 0.0
        if candidate_normalized == query_normalized:
            score = 220.0
        elif candidate_normalized in query_normalized:
            score = 160.0 + min(30.0, len(candidate_normalized) * 1.5)
        elif query_normalized in candidate_normalized:
            score = 135.0 + min(25.0, len(query_normalized))
        else:
            for candidate_token in candidate_tokens:
                if candidate_token in query_tokens:
                    score += 38.0
                    continue
                if len(candidate_token) >= 4 and any(
                    token.startswith(candidate_token)
                    or candidate_token.startswith(token)
                    for token in query_tokens
                    if len(token) >= 4
                ):
                    score += 24.0

        best = max(best, score)

    return best if best > 0 else None


def _best_element(
    annotation: dict[str, Any],
    query: str,
    elements: Iterable[UiElement],
) -> tuple[UiElement, float] | None:
    try:
        original_center = (
            float(annotation.get("x", 0))
            + float(annotation.get("width", 0)) / 2,
            float(annotation.get("y", 0))
            + float(annotation.get("height", 0)) / 2,
        )
    except (TypeError, ValueError):
        original_center = (0.5, 0.5)

    ranked: list[tuple[float, UiElement]] = []
    for element in elements:
        lexical = _lexical_score(query, element)
        if lexical is None:
            continue

        center_x, center_y = element.center
        distance = (
            (center_x - original_center[0]) ** 2
            + (center_y - original_center[1]) ** 2
        ) ** 0.5
        interactive_bonus = (
            18.0
            if element.control_type in INTERACTIVE_CONTROL_TYPES
            else 0.0
        )
        area = element.width * element.height
        oversized_penalty = (
            45.0
            if area > 0.35
            else max(0.0, area - 0.08) * 80
        )
        score = lexical + interactive_bonus - distance * 22 - oversized_penalty
        ranked.append((score, element))

    if not ranked:
        return None

    ranked.sort(key=lambda item: item[0], reverse=True)
    score, element = ranked[0]
    if score < 24:
        return None
    return element, score


def ground_screen_annotations(
    annotations: object,
    action: object,
    elements: Iterable[UiElement],
) -> tuple[list[dict[str, Any]], set[str], list[UiGroundingMatch]]:
    """Replace model-estimated boxes with verified physical UI rectangles."""
    if not isinstance(annotations, list):
        return [], set(), []

    element_list = list(elements)
    target_id = ""
    action_label = ""
    if isinstance(action, dict):
        target_id = _clean_text(action.get("target_id"), 40)
        action_label = _clean_text(action.get("label"), 120)

    grounded: list[dict[str, Any]] = []
    verified_ids: set[str] = set()
    matches: list[UiGroundingMatch] = []

    for raw in annotations:
        if not isinstance(raw, dict):
            continue
        annotation = dict(raw)
        annotation_id = _clean_text(annotation.get("id"), 40)
        label = _clean_text(annotation.get("label"), 120)
        kind = _clean_text(annotation.get("kind"), 20).lower()
        query = label
        if annotation_id and annotation_id == target_id:
            query = f"{label} {action_label}".strip()

        if kind in GROUNDABLE_ANNOTATION_KINDS and query and element_list:
            match = _best_element(annotation, query, element_list)
            if match is not None:
                element, score = match
                annotation.update({
                    "x": element.x,
                    "y": element.y,
                    "width": element.width,
                    "height": element.height,
                })
                if annotation_id:
                    verified_ids.add(annotation_id)
                    matches.append(UiGroundingMatch(
                        annotation_id=annotation_id,
                        annotation_label=label,
                        element_name=element.name,
                        control_type=element.control_type,
                        score=score,
                    ))

        grounded.append(annotation)

    return grounded, verified_ids, matches
