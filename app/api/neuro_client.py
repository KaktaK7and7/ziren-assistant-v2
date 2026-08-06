import base64
import io
import re
import threading
from dataclasses import dataclass
from typing import Any

import httpx

from app.api.desktop_auth import (
    DesktopAuthenticationError,
    desktop_authorization_headers,
    normalize_desktop_token,
)
from app.config.settings import AUTH_SITE_URL, DESKTOP_TOKEN_ENV, get_desktop_token


MIN_SCREEN_ANNOTATION_CONFIDENCE = 0.78
MAX_VISUAL_TARGET_WIDTH = 0.4
MAX_VISUAL_TARGET_HEIGHT = 0.3
SCREEN_CROP_PREFIX = "data:image/jpeg;base64,"
MAX_SCREEN_CROP_BYTES = 1_200_000
TARGET_TOKEN_RE = re.compile(r"[0-9a-zа-яё_]+", re.IGNORECASE)
IGNORED_TARGET_TOKENS = {
    "кнопка",
    "кнопку",
    "вкладка",
    "вкладку",
    "пункт",
    "пункта",
    "меню",
    "ссылка",
    "ссылку",
    "иконка",
    "иконку",
    "элемент",
    "элемента",
    "экран",
    "экране",
}


class NeuroAuthenticationError(RuntimeError):
    """The desktop session is no longer accepted by the assistant gateway."""


@dataclass(frozen=True)
class NeuroMessageResult:
    answer: str
    drawing_request: dict[str, Any] | None = None


@dataclass(frozen=True)
class ScreenMessageResult:
    answer: str
    mode: str
    annotations: list[dict[str, Any]]
    action: dict[str, Any]


@dataclass(frozen=True)
class _ScreenCropTransform:
    left: float
    top: float
    width: float
    height: float


def _clean_text(value: object, limit: int = 180) -> str:
    safe = re.sub(r"[\x00-\x1f\x7f]", " ", str(value or ""))
    return " ".join(safe.split())[:limit].strip()


def _annotation_confidence(annotation: object) -> float:
    if not isinstance(annotation, dict):
        return 0.0
    value = annotation.get("confidence", 1.0)
    if isinstance(value, bool):
        return 0.0
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0
    return min(1.0, max(0.0, confidence))


def _target_tokens(value: object) -> set[str]:
    return {
        token
        for token in TARGET_TOKEN_RE.findall(_clean_text(value).casefold())
        if len(token) >= 3 and token not in IGNORED_TARGET_TOKENS
    }


def _tokens_match(left: str, right: str) -> bool:
    if left == right:
        return True
    prefix_length = min(6, len(left), len(right))
    return (
        prefix_length >= 4
        and (
            left[:prefix_length] == right[:prefix_length]
            or left in right
            or right in left
        )
    )


def _annotation_label_matches(
    expected_label: object,
    candidate_label: object,
) -> bool:
    expected = _target_tokens(expected_label)
    candidate = _target_tokens(candidate_label)
    if not expected or not candidate:
        return False
    return any(
        _tokens_match(left, right)
        for left in expected
        for right in candidate
    )


def _valid_annotation_box(annotation: object) -> tuple[float, float, float, float] | None:
    if not isinstance(annotation, dict):
        return None
    try:
        x = float(annotation.get("x"))
        y = float(annotation.get("y"))
        width = float(annotation.get("width"))
        height = float(annotation.get("height"))
    except (TypeError, ValueError):
        return None
    if (
        x < 0
        or y < 0
        or width <= 0
        or height <= 0
        or x > 1
        or y > 1
    ):
        return None
    width = min(width, 1 - x)
    height = min(height, 1 - y)
    if width <= 0 or height <= 0:
        return None
    return x, y, width, height


def _select_retry_annotation(data: dict[str, Any]) -> dict[str, Any] | None:
    annotations = data.get("annotations")
    if not isinstance(annotations, list):
        return None

    action = data.get("action")
    target_id = ""
    if isinstance(action, dict):
        target_id = str(action.get("target_id") or "").strip()

    candidates = [
        item
        for item in annotations
        if isinstance(item, dict)
        and str(item.get("kind") or "").lower() in {"target", "step"}
        and _valid_annotation_box(item) is not None
    ]
    if not candidates:
        return None

    if target_id:
        for item in candidates:
            if str(item.get("id") or "").strip() == target_id:
                return item

    candidates.sort(
        key=lambda item: (
            _annotation_confidence(item),
            -(
                float(item.get("width", 1))
                * float(item.get("height", 1))
            ),
        ),
        reverse=True,
    )
    return candidates[0]


def _needs_enlarged_crop(data: dict[str, Any]) -> bool:
    """Every visual target needs a second, zoomed localization pass."""
    return _select_retry_annotation(data) is not None


def _build_enlarged_screen_crop(
    image_data_url: str,
    annotation: dict[str, Any],
) -> tuple[str, _ScreenCropTransform] | None:
    if not image_data_url.startswith(SCREEN_CROP_PREFIX):
        return None
    box = _valid_annotation_box(annotation)
    if box is None:
        return None

    from PIL import Image

    try:
        raw = base64.b64decode(
            image_data_url[len(SCREEN_CROP_PREFIX):],
            validate=True,
        )
        image = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:
        return None

    x, y, width, height = box
    center_x = x + width / 2
    center_y = y + height / 2
    # A model can be confidently wrong by 10–20% of the screen. Keep the
    # verification crop deliberately broad and inspect the whole fragment.
    crop_width = min(0.92, max(0.60, width * 6.0))
    crop_height = min(0.82, max(0.50, height * 6.0))
    left = min(1 - crop_width, max(0.0, center_x - crop_width / 2))
    top = min(1 - crop_height, max(0.0, center_y - crop_height / 2))

    pixel_left = round(left * image.width)
    pixel_top = round(top * image.height)
    pixel_right = round((left + crop_width) * image.width)
    pixel_bottom = round((top + crop_height) * image.height)
    if pixel_right - pixel_left < 8 or pixel_bottom - pixel_top < 8:
        return None

    crop = image.crop((pixel_left, pixel_top, pixel_right, pixel_bottom))
    scale = min(1600 / crop.width, 900 / crop.height)
    if scale > 1.0:
        crop = crop.resize(
            (
                max(1, round(crop.width * scale)),
                max(1, round(crop.height * scale)),
            ),
            Image.Resampling.LANCZOS,
        )

    encoded = b""
    for quality in (82, 72, 62, 52):
        buffer = io.BytesIO()
        crop.save(
            buffer,
            format="JPEG",
            quality=quality,
            optimize=True,
            progressive=True,
        )
        encoded = buffer.getvalue()
        if len(encoded) <= MAX_SCREEN_CROP_BYTES:
            break

    if not encoded or len(encoded) > MAX_SCREEN_CROP_BYTES:
        return None

    return (
        SCREEN_CROP_PREFIX + base64.b64encode(encoded).decode("ascii"),
        _ScreenCropTransform(
            left=left,
            top=top,
            width=crop_width,
            height=crop_height,
        ),
    )


def _remap_crop_annotations(
    data: dict[str, Any],
    transform: _ScreenCropTransform,
) -> dict[str, Any]:
    annotations = data.get("annotations")
    if not isinstance(annotations, list):
        return data

    remapped: list[dict[str, Any]] = []
    for raw in annotations:
        box = _valid_annotation_box(raw)
        if box is None or not isinstance(raw, dict):
            continue
        x, y, width, height = box
        item = dict(raw)
        item.update({
            "x": transform.left + x * transform.width,
            "y": transform.top + y * transform.height,
            "width": width * transform.width,
            "height": height * transform.height,
        })
        remapped.append(item)

    result = dict(data)
    result["annotations"] = remapped
    return result


def _merge_refined_annotation(
    original: dict[str, Any],
    refined: object,
) -> dict[str, Any] | None:
    original_box = _valid_annotation_box(original)
    refined_box = _valid_annotation_box(refined)
    if (
        original_box is None
        or refined_box is None
        or not isinstance(refined, dict)
        or _annotation_confidence(refined)
        < MIN_SCREEN_ANNOTATION_CONFIDENCE
        or not _annotation_label_matches(
            original.get("label"),
            refined.get("label"),
        )
    ):
        return None

    x, y, width, height = refined_box
    if (
        width > MAX_VISUAL_TARGET_WIDTH
        or height > MAX_VISUAL_TARGET_HEIGHT
    ):
        return None

    result = dict(original)
    result.update({
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "confidence": _annotation_confidence(refined),
        "_visual_refined": True,
    })
    return result


def _replace_annotation(
    data: dict[str, Any],
    original: dict[str, Any],
    refined: dict[str, Any],
) -> dict[str, Any]:
    original_id = _clean_text(original.get("id"), 40)
    annotations = data.get("annotations")
    if not isinstance(annotations, list):
        return data

    replaced: list[dict[str, Any]] = []
    for item in annotations:
        if (
            isinstance(item, dict)
            and _clean_text(item.get("id"), 40) == original_id
        ):
            replaced.append(refined)
        elif isinstance(item, dict):
            replaced.append(dict(item))

    result = dict(data)
    result["annotations"] = replaced
    return result


def _mark_unverified_targets(data: dict[str, Any]) -> dict[str, Any]:
    """Prevent a first-pass model box from becoming a visual fallback."""
    annotations = data.get("annotations")
    if not isinstance(annotations, list):
        return data

    normalized: list[dict[str, Any]] = []
    for raw in annotations:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        if str(item.get("kind") or "").lower() in {"target", "step"}:
            item["confidence"] = 0.0
            item.pop("_visual_refined", None)
        normalized.append(item)

    result = dict(data)
    result["annotations"] = normalized
    return result


def _target_status_answer(annotation: dict[str, Any]) -> str:
    label = _clean_text(annotation.get("label"), 100) or "цели"
    return (
        f"Проверила расположение «{label}». "
        "На экране отображается только подтверждённая рамка."
    )


def _screen_result_from_data(data: dict[str, Any]) -> ScreenMessageResult:
    annotations = data.get("annotations")
    action = data.get("action")
    return ScreenMessageResult(
        answer=str(data.get("answer", "")),
        mode=str(data.get("mode", "explain")),
        annotations=(
            annotations
            if isinstance(annotations, list)
            else []
        ),
        action=(
            action
            if isinstance(action, dict)
            else {
                "type": "none",
                "risk": "blocked",
                "reason": "Действие не предложено.",
            }
        ),
    )


class NeuroClient:
    def __init__(
        self,
        session_id: int | None = None,
        desktop_token: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.session_id = session_id
        self.desktop_token = normalize_desktop_token(
            desktop_token or get_desktop_token()
        )

        try:
            self.authorization_headers = desktop_authorization_headers(
                self.desktop_token
            )
        except DesktopAuthenticationError as error:
            raise RuntimeError(f"{error} ({DESKTOP_TOKEN_ENV})") from error

        self.client = client or httpx.Client(
            base_url=AUTH_SITE_URL,
            timeout=30.0,
        )
        self._session_lock = threading.Lock()
        self._chat_lock = threading.Lock()
        self._drawing_lock = threading.Lock()
        self._delivered_companion_lines: list[str] = []

    def _get_session_id(self) -> int | None:
        with self._session_lock:
            return self.session_id

    def _update_session_id(
        self,
        request_session_id: int | None,
        response_session_id: object,
    ) -> None:
        if not isinstance(response_session_id, int):
            return

        with self._session_lock:
            if request_session_id is None and self.session_id is not None:
                return

            self.session_id = response_session_id

    def mark_companion_line_delivered(self, line: str) -> None:
        safe_line = "".join(
            character
            if character >= " " and character != "\x7f"
            else " "
            for character in str(line or "")
        )
        normalized = " ".join(safe_line.split())[:600]

        if not normalized:
            return

        with self._session_lock:
            self._delivered_companion_lines.append(normalized)
            self._delivered_companion_lines = (
                self._delivered_companion_lines[-2:]
            )

    def _get_chat_context(self) -> tuple[int | None, list[str]]:
        with self._session_lock:
            return (
                self.session_id,
                list(self._delivered_companion_lines),
            )

    def _forget_delivered_lines(self, delivered_lines: list[str]) -> None:
        if not delivered_lines:
            return

        with self._session_lock:
            for delivered_line in delivered_lines:
                try:
                    self._delivered_companion_lines.remove(delivered_line)
                except ValueError:
                    continue

    def _post(
        self,
        path: str,
        payload: dict,
        timeout: float | None = None,
    ) -> dict:
        request_session_id = payload.get("session_id")
        request_options = {
            "headers": self.authorization_headers,
            "json": payload,
        }

        if timeout is not None:
            request_options["timeout"] = timeout

        response = self.client.post(path, **request_options)

        if response.status_code in (401, 403):
            raise NeuroAuthenticationError(
                "Desktop session is no longer authorized"
            )

        response.raise_for_status()
        data = response.json()

        if isinstance(data, dict):
            self._update_session_id(
                request_session_id,
                data.get("session_id"),
            )
            return data

        return {}

    def send_message(
        self,
        message: str,
        capabilities: list[dict] | None = None,
    ) -> str:
        return self.send_message_result(message, capabilities).answer

    def send_message_result(
        self,
        message: str,
        capabilities: list[dict] | None = None,
    ) -> NeuroMessageResult:
        with self._chat_lock:
            session_id, delivered_lines = self._get_chat_context()
            data = self._post(
                "/api/assistant/chat",
                {
                    "message": message,
                    "session_id": session_id,
                    "preceding_assistant_lines": delivered_lines,
                    "capabilities": capabilities or [],
                },
            )
            self._forget_delivered_lines(delivered_lines)

        drawing_request = data.get("drawing_request")
        return NeuroMessageResult(
            answer=str(data.get("answer", "")),
            drawing_request=(
                drawing_request
                if isinstance(drawing_request, dict)
                else None
            ),
        )

    def send_screen_message(
        self,
        message: str,
        image_data_url: str,
        capabilities: list[dict] | None = None,
    ) -> ScreenMessageResult:
        with self._chat_lock:
            session_id, delivered_lines = self._get_chat_context()
            data = self._post(
                "/api/assistant/vision",
                {
                    "message": message,
                    "image_data_url": image_data_url,
                    "session_id": session_id,
                    "preceding_assistant_lines": delivered_lines,
                    "capabilities": capabilities or [],
                },
            )
            self._forget_delivered_lines(delivered_lines)

            retry_annotation = (
                _select_retry_annotation(data)
                if _needs_enlarged_crop(data)
                else None
            )
            if retry_annotation is not None:
                # The first box is only a crop hint. It must never reach the
                # overlay before the zoomed pass confirms it.
                data = _mark_unverified_targets(data)
                data["answer"] = _target_status_answer(retry_annotation)

            crop_result = (
                _build_enlarged_screen_crop(
                    image_data_url,
                    retry_annotation,
                )
                if retry_annotation is not None
                else None
            )
            if crop_result is not None and retry_annotation is not None:
                crop_data_url, transform = crop_result
                retry_data = self._post(
                    "/api/assistant/vision",
                    {
                        "message": (
                            f"{message}\n\n"
                            "Служебное уточнение: это увеличенный фрагмент "
                            "предыдущего снимка вокруг вероятной цели. "
                            f"Ищи только реально видимый элемент «"
                            f"{_clean_text(retry_annotation.get('label'), 100)}"
                            "». Первая рамка недоверенная: не используй её "
                            "координаты и не предполагай, что цель находится "
                            "в центре. Осмотри весь фрагмент, включая края. "
                            "Верни ровно одну плотную рамку target/step только "
                            "если видишь совпадающий текст или значок. Если "
                            "цели нет — верни пустой annotations."
                        ),
                        "image_data_url": crop_data_url,
                        "session_id": self._get_session_id(),
                        "preceding_assistant_lines": [],
                        "capabilities": capabilities or [],
                    },
                )
                retry_data = _remap_crop_annotations(
                    retry_data,
                    transform,
                )
                retry_candidate = _select_retry_annotation(retry_data)
                refined = _merge_refined_annotation(
                    retry_annotation,
                    retry_candidate,
                )
                if refined is not None:
                    data = _replace_annotation(
                        data,
                        retry_annotation,
                        refined,
                    )

        return _screen_result_from_data(data)

    def request_command_reaction(
        self,
        feature_id: str,
        subject_label: str,
        result_text: str,
        capabilities: list[dict] | None = None,
    ) -> str:
        data = self._post(
            "/api/assistant/reaction",
            {
                "feature_id": feature_id,
                "subject_label": subject_label,
                "result_text": result_text,
                "session_id": self._get_session_id(),
                "capabilities": capabilities or [],
            },
        )
        return str(data.get("text", ""))

    def request_proactive(
        self,
        idle_minutes: int,
        capabilities: list[dict] | None = None,
    ) -> str:
        data = self._post(
            "/api/assistant/proactive",
            {
                "idle_minutes": idle_minutes,
                "session_id": self._get_session_id(),
                "capabilities": capabilities or [],
            },
        )
        return str(data.get("text", ""))

    def generate_drawing(
        self,
        drawing_request: dict[str, Any],
    ) -> dict[str, Any]:
        with self._drawing_lock:
            return self._post(
                "/api/assistant/drawings/generate",
                drawing_request,
                timeout=125.0,
            )
