from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse


BROWSER_BRIDGE_HOST = "127.0.0.1"
BROWSER_BRIDGE_PORT = int(os.getenv("ZIREN_BROWSER_BRIDGE_PORT", "8788"))
BROWSER_BRIDGE_MAX_BODY_BYTES = 2 * 1024 * 1024
SNAPSHOT_TTL_SECONDS = 3.0
COMMAND_TTL_SECONDS = 8.0
MAX_ELEMENTS = 600
MAX_MEMBER_IDS = 24
MIN_MATCH_SCORE = 120.0
MIN_MATCH_MARGIN = 18.0
TOKEN_RE = re.compile(r"[0-9a-zа-яё_]+", re.IGNORECASE)
EXTENSION_ORIGIN_RE = re.compile(
    r"^(?:chrome|opera|moz)-extension://[a-z0-9_-]+$",
    re.IGNORECASE,
)

GENERIC_QUERY_TOKENS = {
    "а",
    "в",
    "во",
    "вот",
    "где",
    "да",
    "здесь",
    "и",
    "какая",
    "какие",
    "какой",
    "какое",
    "кнопка",
    "кнопку",
    "мелиса",
    "мелисса",
    "меня",
    "мне",
    "мой",
    "моя",
    "моё",
    "на",
    "нарисуй",
    "можно",
    "покажи",
    "показать",
    "подсвети",
    "прям",
    "прямо",
    "странице",
    "страницу",
    "там",
    "тут",
    "ты",
    "экран",
    "экране",
    "это",
    "эта",
    "эту",
    "этот",
}
CHOICE_INTENT_PREFIXES = (
    "выб",
    "интерес",
    "фильтр",
    "настро",
    "диапаз",
    "вариант",
)


def _clean_text(value: object, limit: int = 240) -> str:
    safe = re.sub(r"[\x00-\x1f\x7f]", " ", str(value or ""))
    return " ".join(safe.split())[:limit].strip()


def _tokens(value: object) -> list[str]:
    return [
        token.casefold()
        for token in TOKEN_RE.findall(_clean_text(value).casefold())
        if len(token) >= 2
    ]


def _significant_tokens(value: object) -> list[str]:
    return [
        token
        for token in _tokens(value)
        if token not in GENERIC_QUERY_TOKENS
    ]


def _tokens_match(left: str, right: str) -> bool:
    if left == right:
        return True
    prefix = min(6, len(left), len(right))
    return bool(
        prefix >= 4
        and (
            left[:prefix] == right[:prefix]
            or left in right
            or right in left
        )
    )


def _choice_intent(query_tokens: list[str]) -> bool:
    return any(
        token.startswith(prefix)
        for token in query_tokens
        for prefix in CHOICE_INTENT_PREFIXES
    )


def is_extension_origin(origin: object) -> bool:
    return bool(EXTENSION_ORIGIN_RE.fullmatch(_clean_text(origin, 220)))


def _number(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not (number == number):
        return default
    return number


@dataclass(frozen=True)
class BrowserElement:
    element_id: str
    text: str
    role: str
    interactive: bool
    x: float
    y: float
    width: float
    height: float
    member_ids: tuple[str, ...] = ()

    @property
    def area(self) -> float:
        return self.width * self.height


@dataclass(frozen=True)
class BrowserSnapshot:
    tab_id: int
    url: str
    title: str
    viewport_width: float
    viewport_height: float
    elements: tuple[BrowserElement, ...]
    received_at: float


@dataclass(frozen=True)
class BrowserMatch:
    tab_id: int
    element_id: str
    label: str
    role: str
    score: float
    member_ids: tuple[str, ...]
    url: str


class BrowserBridgeStore:
    """Short-lived DOM snapshots and highlight commands from the browser extension."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._snapshots: dict[int, BrowserSnapshot] = {}
        self._commands: dict[int, tuple[float, dict[str, Any]]] = {}
        self._last_targets: dict[int, BrowserMatch] = {}

    def _normalize_element(
        self,
        raw: object,
        viewport_width: float,
        viewport_height: float,
    ) -> BrowserElement | None:
        if not isinstance(raw, dict):
            return None

        element_id = _clean_text(raw.get("id"), 100)
        text = _clean_text(raw.get("text"), 220)
        role = _clean_text(raw.get("role"), 60).lower() or "text"
        rect = raw.get("rect")
        if not element_id or not text or not isinstance(rect, dict):
            return None

        x = _number(rect.get("x"), -1)
        y = _number(rect.get("y"), -1)
        width = _number(rect.get("width"), -1)
        height = _number(rect.get("height"), -1)
        if (
            x < 0
            or y < 0
            or width < 2
            or height < 2
            or viewport_width <= 0
            or viewport_height <= 0
        ):
            return None

        x = min(1.0, max(0.0, x / viewport_width))
        y = min(1.0, max(0.0, y / viewport_height))
        width = min(1.0 - x, max(0.0, width / viewport_width))
        height = min(1.0 - y, max(0.0, height / viewport_height))
        if width < 0.002 or height < 0.002:
            return None

        raw_members = raw.get("member_ids")
        member_ids: tuple[str, ...] = ()
        if isinstance(raw_members, list):
            member_ids = tuple(
                member
                for member in (
                    _clean_text(item, 100)
                    for item in raw_members[:MAX_MEMBER_IDS]
                )
                if member
            )

        return BrowserElement(
            element_id=element_id,
            text=text,
            role=role,
            interactive=bool(raw.get("interactive")),
            x=x,
            y=y,
            width=width,
            height=height,
            member_ids=member_ids,
        )

    def update_snapshot(self, payload: object) -> BrowserSnapshot | None:
        if not isinstance(payload, dict):
            return None

        try:
            tab_id = int(payload.get("tab_id"))
        except (TypeError, ValueError):
            return None
        if tab_id < 0:
            return None

        viewport_width = _number(payload.get("viewport_width"), 0)
        viewport_height = _number(payload.get("viewport_height"), 0)
        if viewport_width < 100 or viewport_height < 100:
            return None

        raw_elements = payload.get("elements")
        if not isinstance(raw_elements, list):
            return None

        elements: list[BrowserElement] = []
        seen: set[str] = set()
        for raw in raw_elements[:MAX_ELEMENTS]:
            element = self._normalize_element(
                raw,
                viewport_width,
                viewport_height,
            )
            if element is None or element.element_id in seen:
                continue
            seen.add(element.element_id)
            elements.append(element)

        if not elements:
            return None

        snapshot = BrowserSnapshot(
            tab_id=tab_id,
            url=_clean_text(payload.get("url"), 1000),
            title=_clean_text(payload.get("title"), 240),
            viewport_width=viewport_width,
            viewport_height=viewport_height,
            elements=tuple(elements),
            received_at=self._clock(),
        )
        with self._lock:
            self._snapshots[tab_id] = snapshot
            # Keep only a few tabs. The extension sends the active tab most often.
            if len(self._snapshots) > 8:
                oldest = min(
                    self._snapshots,
                    key=lambda item: self._snapshots[item].received_at,
                )
                self._snapshots.pop(oldest, None)
                self._commands.pop(oldest, None)
                self._last_targets.pop(oldest, None)
        return snapshot

    def _latest_snapshot_locked(self) -> BrowserSnapshot | None:
        now = self._clock()
        fresh = [
            snapshot
            for snapshot in self._snapshots.values()
            if now - snapshot.received_at <= SNAPSHOT_TTL_SECONDS
        ]
        if not fresh:
            return None
        return max(fresh, key=lambda item: item.received_at)

    def latest_snapshot(self) -> BrowserSnapshot | None:
        with self._lock:
            return self._latest_snapshot_locked()

    def has_fresh_snapshot(self) -> bool:
        return self.latest_snapshot() is not None

    @staticmethod
    def _score_element(
        element: BrowserElement,
        query_tokens: list[str],
        choice_intent: bool,
    ) -> float:
        candidate_tokens = _tokens(element.text)
        if not candidate_tokens:
            return 0.0

        exact = 0
        fuzzy = 0
        for query_token in query_tokens:
            if query_token in candidate_tokens:
                exact += 1
            elif any(
                _tokens_match(query_token, candidate)
                for candidate in candidate_tokens
            ):
                fuzzy += 1

        if exact == 0 and fuzzy == 0:
            return 0.0

        score = exact * 120.0 + fuzzy * 72.0
        normalized_text = " ".join(candidate_tokens)
        normalized_query = " ".join(query_tokens)
        if normalized_text and normalized_text in normalized_query:
            score += 100.0

        if element.role == "group" and element.member_ids:
            score += 24.0
            if choice_intent:
                score += 90.0
        elif element.interactive:
            score += 24.0

        # Very large regions are usually page containers rather than targets.
        if element.area > 0.45:
            score -= 160.0
        elif element.area > 0.25:
            score -= 70.0
        return score

    def _last_target_for_snapshot_locked(
        self,
        snapshot: BrowserSnapshot,
    ) -> BrowserMatch | None:
        previous = self._last_targets.get(snapshot.tab_id)
        if previous is None or previous.url != snapshot.url:
            return None
        valid_ids = {element.element_id for element in snapshot.elements}
        if previous.element_id not in valid_ids:
            return None
        return previous

    def resolve(self, query: object) -> BrowserMatch | None:
        query_tokens = _significant_tokens(query)
        raw_tokens = _tokens(query)
        choice_intent = _choice_intent(raw_tokens)

        with self._lock:
            snapshot = self._latest_snapshot_locked()
            if snapshot is None:
                return None

            if not query_tokens:
                return self._last_target_for_snapshot_locked(snapshot)

            ranked: list[tuple[float, BrowserElement]] = []
            for element in snapshot.elements:
                score = self._score_element(
                    element,
                    query_tokens,
                    choice_intent,
                )
                if score > 0:
                    ranked.append((score, element))

            if not ranked:
                # Follow-up phrases often contain only generic verbs plus a word
                # that is absent from the DOM. Prefer the prior grounded target.
                if any(
                    token in {"это", "эту", "этот", "там", "туда", "прям"}
                    for token in raw_tokens
                ):
                    return self._last_target_for_snapshot_locked(snapshot)
                return None

            ranked.sort(key=lambda item: item[0], reverse=True)
            best_score, best = ranked[0]
            runner_up = ranked[1][0] if len(ranked) > 1 else 0.0
            if best_score < MIN_MATCH_SCORE:
                return None
            if runner_up and best_score - runner_up < MIN_MATCH_MARGIN:
                return None

            match = BrowserMatch(
                tab_id=snapshot.tab_id,
                element_id=best.element_id,
                label=best.text,
                role=best.role,
                score=best_score,
                member_ids=best.member_ids,
                url=snapshot.url,
            )
            self._last_targets[snapshot.tab_id] = match
            return match

    def queue_highlight(self, match: BrowserMatch) -> dict[str, Any]:
        command = {
            "type": "highlight",
            "element_id": match.element_id,
            "member_ids": list(match.member_ids),
            "label": match.label,
            "duration_ms": 6500,
        }
        with self._lock:
            self._commands[match.tab_id] = (self._clock(), command)
        return command

    def resolve_and_highlight(self, query: object) -> BrowserMatch | None:
        match = self.resolve(query)
        if match is not None:
            self.queue_highlight(match)
        return match

    def consume_command(self, tab_id: int) -> dict[str, Any] | None:
        with self._lock:
            item = self._commands.pop(tab_id, None)
        if item is None:
            return None
        created_at, command = item
        if self._clock() - created_at > COMMAND_TTL_SECONDS:
            return None
        return dict(command)


def _bridge_answer(match: BrowserMatch) -> str:
    label = _clean_text(match.label, 100) or "нужный элемент"
    if match.role == "group":
        return f"Вот здесь — блок «{label}». Я подсветила его прямо на странице."
    return f"Вот здесь — «{label}». Я подсветила этот элемент прямо на странице."


_store = BrowserBridgeStore()
_server: ThreadingHTTPServer | None = None
_server_lock = threading.Lock()


def get_browser_bridge_store() -> BrowserBridgeStore:
    return _store


def start_browser_bridge_server() -> ThreadingHTTPServer | None:
    global _server
    with _server_lock:
        if _server is not None:
            return _server

        store = _store

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args) -> None:
                return

            def _origin(self) -> str:
                return _clean_text(self.headers.get("Origin"), 220)

            def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
                encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                origin = self._origin()
                if is_extension_origin(origin):
                    self.send_header("Access-Control-Allow-Origin", origin)
                    self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def _authorized(self) -> bool:
                if is_extension_origin(self._origin()):
                    return True
                self._send_json(
                    {"ok": False, "error": "extension origin required"},
                    status=403,
                )
                return False

            def do_OPTIONS(self) -> None:
                if not self._authorized():
                    return
                self._send_json({"ok": True})

            def do_GET(self) -> None:
                if not self._authorized():
                    return
                parsed = urlparse(self.path)
                if parsed.path == "/health":
                    self._send_json({"ok": True, "bridge": "ziren-browser"})
                    return
                if parsed.path == "/command":
                    values = parse_qs(parsed.query)
                    try:
                        tab_id = int((values.get("tab_id") or [""])[0])
                    except ValueError:
                        self._send_json(
                            {"ok": False, "error": "invalid tab_id"},
                            status=400,
                        )
                        return
                    self._send_json({
                        "ok": True,
                        "command": store.consume_command(tab_id),
                    })
                    return
                self._send_json({"ok": False, "error": "not found"}, status=404)

            def do_POST(self) -> None:
                if not self._authorized():
                    return
                if urlparse(self.path).path != "/snapshot":
                    self._send_json({"ok": False, "error": "not found"}, status=404)
                    return
                try:
                    content_length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    content_length = 0
                if (
                    content_length <= 0
                    or content_length > BROWSER_BRIDGE_MAX_BODY_BYTES
                ):
                    self._send_json(
                        {"ok": False, "error": "invalid body size"},
                        status=400,
                    )
                    return
                try:
                    payload = json.loads(
                        self.rfile.read(content_length).decode("utf-8"),
                    )
                except Exception:
                    self._send_json(
                        {"ok": False, "error": "invalid json"},
                        status=400,
                    )
                    return
                snapshot = store.update_snapshot(payload)
                if snapshot is None:
                    self._send_json(
                        {"ok": False, "error": "invalid snapshot"},
                        status=400,
                    )
                    return
                self._send_json({
                    "ok": True,
                    "tab_id": snapshot.tab_id,
                    "elements": len(snapshot.elements),
                })

        try:
            server = ThreadingHTTPServer(
                (BROWSER_BRIDGE_HOST, BROWSER_BRIDGE_PORT),
                Handler,
            )
        except OSError as error:
            try:
                from app.core.log_bus import add_log

                add_log(
                    "Browser Bridge не запущен",
                    level="warn",
                    meta={"error": str(error), "port": BROWSER_BRIDGE_PORT},
                )
            except Exception:
                pass
            return None

        _server = server
        threading.Thread(
            target=server.serve_forever,
            daemon=True,
            name="ziren-browser-bridge",
        ).start()
        try:
            from app.core.log_bus import add_log

            add_log(
                "Browser Bridge запущен",
                meta={
                    "url": f"http://{BROWSER_BRIDGE_HOST}:{BROWSER_BRIDGE_PORT}",
                },
            )
        except Exception:
            pass
        return server


def ensure_browser_bridge() -> BrowserBridgeStore:
    start_browser_bridge_server()
    return _store


def browser_bridge_screen_result(query: object) -> dict[str, Any] | None:
    store = ensure_browser_bridge()
    match = store.resolve_and_highlight(query)
    if match is None:
        return None
    try:
        from app.core.log_bus import add_log

        add_log(
            "Browser Bridge точно нашёл элемент страницы",
            meta={
                "label": match.label,
                "role": match.role,
                "score": round(match.score, 1),
                "tab_id": match.tab_id,
            },
        )
    except Exception:
        pass
    return {
        "answer": _bridge_answer(match),
        "mode": "annotate",
        "annotations": [],
        "action": {
            "type": "none",
            "target_id": "",
            "label": match.label,
            "risk": "blocked",
            "reason": (
                "Browser Bridge подсветил DOM-элемент напрямую. "
                "Физический клик в MVP отключён."
            ),
        },
    }
