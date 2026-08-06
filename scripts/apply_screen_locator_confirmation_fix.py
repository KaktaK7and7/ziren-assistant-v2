from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NEURO_CLIENT = ROOT / "app" / "api" / "neuro_client.py"
TEST_FILE = ROOT / "tests" / "test_screen_locator_refine.py"
WORKFLOW = ROOT / ".github" / "workflows" / "apply-screen-locator-confirmation-fix.yml"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, got {count}")
    return text.replace(old, new, 1)


text = NEURO_CLIENT.read_text(encoding="utf-8")
text = replace_once(
    text,
    "import io\nimport threading\n",
    "import io\nimport re\nimport threading\n",
    "import re",
)
text = replace_once(
    text,
    'MIN_SCREEN_ANNOTATION_CONFIDENCE = 0.78\nSCREEN_CROP_PREFIX = "data:image/jpeg;base64,"\nMAX_SCREEN_CROP_BYTES = 1_200_000\n',
    '''MIN_SCREEN_ANNOTATION_CONFIDENCE = 0.78
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
''',
    "locator constants",
)
text = replace_once(
    text,
    "\ndef _annotation_confidence(annotation: object) -> float:\n",
    '''
def _clean_text(value: object, limit: int = 180) -> str:
    safe = re.sub(r"[\\x00-\\x1f\\x7f]", " ", str(value or ""))
    return " ".join(safe.split())[:limit].strip()


def _annotation_confidence(annotation: object) -> float:
''',
    "clean text helper",
)
text = replace_once(
    text,
    "\ndef _valid_annotation_box(annotation: object) -> tuple[float, float, float, float] | None:\n",
    '''
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
''',
    "label match helpers",
)
text = re.sub(
    r"def _needs_enlarged_crop\(data: dict\[str, Any\]\) -> bool:\n(?:    .*\n)+?(?=\n\ndef _build_enlarged_screen_crop)",
    '''def _needs_enlarged_crop(data: dict[str, Any]) -> bool:
    """Every visual target needs a second, zoomed localization pass."""
    return _select_retry_annotation(data) is not None
''',
    text,
    count=1,
)
text = replace_once(
    text,
    "    crop_width = min(0.82, max(0.34, width * 3.2))\n    crop_height = min(0.82, max(0.34, height * 3.2))\n",
    '''    # A model can be confidently wrong by 10–20% of the screen. Keep the
    # verification crop deliberately broad and inspect the whole fragment.
    crop_width = min(0.92, max(0.60, width * 6.0))
    crop_height = min(0.82, max(0.50, height * 6.0))
''',
    "broad verification crop",
)
text = replace_once(
    text,
    "\ndef _screen_result_from_data(data: dict[str, Any]) -> ScreenMessageResult:\n",
    '''
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
''',
    "refined target helpers",
)
start = text.index("            retry_annotation = (")
end = text.index("\n\n        return _screen_result_from_data(data)", start)
old_block = text[start:end]
new_block = '''            retry_annotation = (
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
                            f"{message}\\n\\n"
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
                    )'''
text = text[:start] + new_block + text[end:]
NEURO_CLIENT.write_text(text, encoding="utf-8")

TEST_FILE.write_text('''import base64
import io
import unittest

from PIL import Image

from app.api.neuro_client import (
    MIN_SCREEN_ANNOTATION_CONFIDENCE,
    _build_enlarged_screen_crop,
    _mark_unverified_targets,
    _merge_refined_annotation,
    _needs_enlarged_crop,
    _remap_crop_annotations,
    _select_retry_annotation,
)


def jpeg_data_url(width: int = 1000, height: int = 700) -> str:
    image = Image.new("RGB", (width, height), (20, 30, 40))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    return (
        "data:image/jpeg;base64,"
        + base64.b64encode(buffer.getvalue()).decode("ascii")
    )


def screen_data(confidence: float) -> dict:
    return {
        "annotations": [{
            "id": "assistant-tab",
            "label": "Кнопка Ассистент",
            "kind": "target",
            "x": 0.80,
            "y": 0.05,
            "width": 0.10,
            "height": 0.06,
            "step": 0,
            "confidence": confidence,
        }],
        "action": {
            "type": "click",
            "target_id": "assistant-tab",
            "label": "Ассистент",
            "risk": "safe",
            "reason": "",
        },
    }


class ScreenLocatorRefineTests(unittest.TestCase):
    def test_every_target_requests_zoomed_verification(self) -> None:
        self.assertTrue(_needs_enlarged_crop(screen_data(0.25)))
        self.assertTrue(_needs_enlarged_crop(screen_data(0.99)))
        data = screen_data(0.9)
        data["annotations"][0].pop("confidence")
        self.assertTrue(_needs_enlarged_crop(data))

    def test_action_target_is_selected_before_other_annotations(self) -> None:
        data = screen_data(0.6)
        data["annotations"].insert(0, {
            "id": "other",
            "label": "Сообщество",
            "kind": "target",
            "x": 0.2,
            "y": 0.2,
            "width": 0.1,
            "height": 0.05,
            "confidence": 0.95,
        })
        selected = _select_retry_annotation(data)
        self.assertIsNotNone(selected)
        self.assertEqual(selected["id"], "assistant-tab")

    def test_first_pass_target_is_disabled_as_visual_fallback(self) -> None:
        marked = _mark_unverified_targets(screen_data(0.99))
        annotation = marked["annotations"][0]
        self.assertEqual(annotation["confidence"], 0.0)
        self.assertNotIn("_visual_refined", annotation)

    def test_crop_covers_smoke_test_coordinate_error(self) -> None:
        result = _build_enlarged_screen_crop(
            jpeg_data_url(),
            screen_data(0.99)["annotations"][0],
        )
        self.assertIsNotNone(result)
        crop_data_url, transform = result
        self.assertTrue(crop_data_url.startswith("data:image/jpeg;base64,"))
        self.assertLessEqual(transform.left, 0.63)
        self.assertLessEqual(transform.top, 0.14)
        self.assertGreaterEqual(transform.left + transform.width, 0.90)
        self.assertGreaterEqual(transform.top + transform.height, 0.20)
        raw = base64.b64decode(crop_data_url.split(",", 1)[1])
        image = Image.open(io.BytesIO(raw))
        self.assertEqual(image.format, "JPEG")

    def test_crop_coordinates_are_remapped_to_full_screen(self) -> None:
        data = {
            "annotations": [{
                "id": "assistant-tab",
                "label": "Ассистент",
                "kind": "target",
                "x": 0.25,
                "y": 0.5,
                "width": 0.2,
                "height": 0.1,
                "confidence": 0.91,
            }],
        }
        original = screen_data(0.4)["annotations"][0]
        crop_result = _build_enlarged_screen_crop(jpeg_data_url(), original)
        self.assertIsNotNone(crop_result)
        _, transform = crop_result
        remapped = _remap_crop_annotations(data, transform)
        annotation = remapped["annotations"][0]
        self.assertAlmostEqual(
            annotation["x"],
            transform.left + 0.25 * transform.width,
        )
        self.assertAlmostEqual(
            annotation["y"],
            transform.top + 0.5 * transform.height,
        )
        self.assertAlmostEqual(
            annotation["width"],
            0.2 * transform.width,
        )

    def test_matching_zoomed_result_becomes_visual_only_verified(self) -> None:
        original = screen_data(0.99)["annotations"][0]
        refined = {
            "id": "different-service-id",
            "label": "Ассистент",
            "kind": "target",
            "x": 0.625,
            "y": 0.115,
            "width": 0.065,
            "height": 0.035,
            "step": 0,
            "confidence": 0.88,
        }
        merged = _merge_refined_annotation(original, refined)
        self.assertIsNotNone(merged)
        self.assertEqual(merged["id"], "assistant-tab")
        self.assertEqual(merged["label"], "Кнопка Ассистент")
        self.assertAlmostEqual(merged["x"], 0.625)
        self.assertTrue(merged["_visual_refined"])
        self.assertGreaterEqual(
            merged["confidence"],
            MIN_SCREEN_ANNOTATION_CONFIDENCE,
        )

    def test_unrelated_or_uncertain_zoomed_result_is_rejected(self) -> None:
        original = screen_data(0.99)["annotations"][0]
        unrelated = dict(original)
        unrelated.update({
            "label": "Сообщество",
            "x": 0.5,
            "confidence": 0.95,
        })
        self.assertIsNone(_merge_refined_annotation(original, unrelated))
        uncertain = dict(original)
        uncertain.update({
            "label": "Ассистент",
            "x": 0.63,
            "confidence": MIN_SCREEN_ANNOTATION_CONFIDENCE - 0.01,
        })
        self.assertIsNone(_merge_refined_annotation(original, uncertain))


if __name__ == "__main__":
    unittest.main()
''', encoding="utf-8")

Path(__file__).unlink()
WORKFLOW.unlink()
