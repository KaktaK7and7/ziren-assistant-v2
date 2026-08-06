from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "app" / "api" / "neuro_client.py"
TESTS = ROOT / "tests" / "test_screen_locator_refine.py"
WORKFLOW = ROOT / ".github" / "workflows" / "apply-screen-answer-guard-fix.yml"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, got {count}")
    return text.replace(old, new, 1)


text = CLIENT.read_text(encoding="utf-8")
text = replace_once(
    text,
    "\ndef _target_status_answer(annotation: dict[str, Any]) -> str:\n",
    '''
def _answer_claims_unverified_location(value: object) -> bool:
    normalized = _clean_text(value, 5000).casefold()
    if not normalized:
        return False
    coordinate_claim = bool(
        re.search(r"\\b0[.,]\\d+\\b", normalized)
        or "от ширины" in normalized
        or "от высоты" in normalized
    )
    visual_claim = any(
        marker in normalized
        for marker in (
            "обвел",
            "обвёл",
            "выделил",
            "подсветил",
            "показал рамк",
            "показываю рамк",
        )
    )
    return coordinate_claim or visual_claim


def _target_status_answer(annotation: dict[str, Any]) -> str:
''',
    "answer guard helper",
)
text = replace_once(
    text,
    '''                data = _mark_unverified_targets(data)
                data["answer"] = _target_status_answer(retry_annotation)
''',
    '''                data = _mark_unverified_targets(data)
                if _answer_claims_unverified_location(data.get("answer")):
                    data["answer"] = _target_status_answer(retry_annotation)
''',
    "conditional answer replacement",
)
CLIENT.write_text(text, encoding="utf-8")

text = TESTS.read_text(encoding="utf-8")
text = replace_once(
    text,
    "    _build_enlarged_screen_crop,\n",
    "    _answer_claims_unverified_location,\n    _build_enlarged_screen_crop,\n",
    "test import",
)
text = replace_once(
    text,
    "class ScreenLocatorRefineTests(unittest.TestCase):\n",
    '''class ScreenLocatorRefineTests(unittest.TestCase):
    def test_only_unverified_location_claims_are_rewritten(self) -> None:
        self.assertFalse(
            _answer_claims_unverified_location("Вижу окно настроек."),
        )
        self.assertTrue(
            _answer_claims_unverified_location(
                "Кнопка примерно в 0.8 от ширины экрана.",
            ),
        )
        self.assertTrue(
            _answer_claims_unverified_location("Я обвела кнопку рамкой."),
        )

''',
    "answer guard tests",
)
TESTS.write_text(text, encoding="utf-8")

Path(__file__).unlink()
WORKFLOW.unlink()
