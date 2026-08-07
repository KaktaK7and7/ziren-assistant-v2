import unittest

from app.vision.browser_bridge import (
    BrowserBridgeStore,
    SNAPSHOT_TTL_SECONDS,
    is_extension_origin,
)


class FakeClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def element(
    element_id: str,
    text: str,
    *,
    role: str = "text",
    interactive: bool = False,
    x: int = 100,
    y: int = 100,
    width: int = 120,
    height: int = 30,
    member_ids: list[str] | None = None,
) -> dict:
    return {
        "id": element_id,
        "text": text,
        "role": role,
        "interactive": interactive,
        "rect": {
            "x": x,
            "y": y,
            "width": width,
            "height": height,
        },
        "member_ids": member_ids or [],
    }


def snapshot(elements: list[dict], tab_id: int = 7) -> dict:
    return {
        "tab_id": tab_id,
        "url": "https://example.test/projects",
        "title": "Projects",
        "viewport_width": 1600,
        "viewport_height": 900,
        "elements": elements,
    }


class BrowserBridgeTests(unittest.TestCase):
    def test_only_extension_origins_are_accepted(self) -> None:
        self.assertTrue(is_extension_origin("chrome-extension://abcdef"))
        self.assertTrue(is_extension_origin("opera-extension://abc123"))
        self.assertFalse(is_extension_origin("https://example.test"))
        self.assertFalse(is_extension_origin("http://127.0.0.1:8788"))
        self.assertFalse(is_extension_origin(""))

    def test_budget_choice_prefers_group_over_heading(self) -> None:
        store = BrowserBridgeStore()
        stored = store.update_snapshot(snapshot([
            element("budget-heading", "Бюджет", x=380, y=580),
            element(
                "budget-group",
                "Бюджет",
                role="group",
                x=375,
                y=575,
                width=210,
                height=260,
                member_ids=["budget-heading", "c1", "c2", "c3"],
            ),
            element(
                "c1",
                "До 1 000 ₽",
                role="checkbox",
                interactive=True,
                x=395,
                y=610,
            ),
            element(
                "c2",
                "От 1 000 ₽ до 3 000 ₽",
                role="checkbox",
                interactive=True,
                x=395,
                y=645,
                width=180,
            ),
            element(
                "c3",
                "От 3 000 ₽ до 10 000 ₽",
                role="checkbox",
                interactive=True,
                x=395,
                y=680,
                width=190,
            ),
        ]))
        self.assertIsNotNone(stored)

        match = store.resolve(
            "Мелисса, покажи мне где здесь можно выбрать какой бюджет меня интересует",
        )

        self.assertIsNotNone(match)
        self.assertEqual(match.element_id, "budget-group")
        self.assertEqual(match.role, "group")
        self.assertIn("c2", match.member_ids)

    def test_named_browser_link_is_selected_without_coordinates_from_ai(self) -> None:
        store = BrowserBridgeStore()
        store.update_snapshot(snapshot([
            element(
                "community",
                "Сообщество",
                role="link",
                interactive=True,
                x=880,
                y=110,
            ),
            element(
                "assistant",
                "Ассистент",
                role="link",
                interactive=True,
                x=1000,
                y=110,
            ),
        ]))

        match = store.resolve("покажи где кнопка Ассистент на экране")

        self.assertIsNotNone(match)
        self.assertEqual(match.element_id, "assistant")
        self.assertGreater(match.score, 200)

    def test_generic_followup_reuses_last_grounded_dom_target(self) -> None:
        store = BrowserBridgeStore()
        store.update_snapshot(snapshot([
            element(
                "budget",
                "Бюджет",
                role="group",
                member_ids=["c1", "c2"],
            ),
            element("c1", "До 1 000 ₽", role="checkbox", interactive=True),
            element("c2", "До 3 000 ₽", role="checkbox", interactive=True),
        ]))
        first = store.resolve("покажи где выбрать бюджет")
        self.assertIsNotNone(first)

        followup = store.resolve("нарисуй мне на экране это покажи прям")

        self.assertIsNotNone(followup)
        self.assertEqual(followup.element_id, first.element_id)

    def test_highlight_command_is_single_use(self) -> None:
        store = BrowserBridgeStore()
        store.update_snapshot(snapshot([
            element(
                "assistant",
                "Ассистент",
                role="link",
                interactive=True,
            ),
        ]))
        match = store.resolve("покажи Ассистент")
        self.assertIsNotNone(match)
        store.queue_highlight(match)

        command = store.consume_command(7)

        self.assertIsNotNone(command)
        self.assertEqual(command["type"], "highlight")
        self.assertEqual(command["element_id"], "assistant")
        self.assertIsNone(store.consume_command(7))

    def test_stale_snapshot_is_not_used(self) -> None:
        clock = FakeClock()
        store = BrowserBridgeStore(clock=clock)
        store.update_snapshot(snapshot([
            element(
                "assistant",
                "Ассистент",
                role="link",
                interactive=True,
            ),
        ]))
        clock.advance(SNAPSHOT_TTL_SECONDS + 0.1)

        self.assertIsNone(store.resolve("покажи Ассистент"))
        self.assertFalse(store.has_fresh_snapshot())


if __name__ == "__main__":
    unittest.main()
