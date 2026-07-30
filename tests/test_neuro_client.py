import unittest
import threading
import time

import httpx

from app.api.neuro_client import NeuroAuthenticationError, NeuroClient


class NeuroClientTests(unittest.TestCase):
    def make_client(self, handler) -> NeuroClient:
        transport = httpx.MockTransport(handler)
        http_client = httpx.Client(
            base_url="https://ziren.test",
            transport=transport,
        )
        return NeuroClient(
            desktop_token="desktop-secret",
            client=http_client,
        )

    def test_sends_desktop_authorization_header(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(
                request.headers.get("Authorization"),
                "Bearer desktop-secret",
            )
            payload = __import__("json").loads(request.content)
            self.assertEqual(
                payload["capabilities"][0]["feature_id"],
                "system.volume",
            )
            return httpx.Response(
                200,
                json={"answer": "Я здесь.", "session_id": 7},
            )

        client = self.make_client(handler)

        self.assertEqual(
            client.send_message(
                "ты тут",
                capabilities=[{
                    "feature_id": "system.volume",
                    "display_name": "Громкость",
                    "actions": ["Громче"],
                }],
            ),
            "Я здесь.",
        )
        self.assertEqual(client.session_id, 7)

    def test_reports_expired_desktop_session_separately(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "Not authenticated"})

        client = self.make_client(handler)

        with self.assertRaises(NeuroAuthenticationError):
            client.send_message("ты тут")

    def test_requests_command_reactions_and_proactive_lines(self) -> None:
        requested_paths = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested_paths.append(request.url.path)
            return httpx.Response(
                200,
                json={"text": "Рядом.", "session_id": 9},
            )

        client = self.make_client(handler)

        self.assertEqual(
            client.request_command_reaction(
                "system.media_control",
                "включи музыку",
                "Открываю плейлист.",
            ),
            "Рядом.",
        )
        self.assertEqual(client.request_proactive(25), "Рядом.")
        self.assertEqual(
            requested_paths,
            ["/api/assistant/reaction", "/api/assistant/proactive"],
        )
        self.assertEqual(client.session_id, 9)

    def test_background_request_does_not_block_user_chat(self) -> None:
        reaction_started = threading.Event()
        release_reaction = threading.Event()

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/assistant/reaction":
                reaction_started.set()
                release_reaction.wait(timeout=2)
                return httpx.Response(
                    200,
                    json={"text": "Позже.", "session_id": 7},
                )

            return httpx.Response(
                200,
                json={"answer": "Сразу.", "session_id": 7},
            )

        client = self.make_client(handler)
        background = threading.Thread(
            target=lambda: client.request_command_reaction(
                "system.volume",
                "сделай громче",
                "Сделала громче.",
            ),
            daemon=True,
        )
        background.start()
        self.assertTrue(reaction_started.wait(timeout=1))

        started_at = time.monotonic()
        self.assertEqual(client.send_message("ты тут"), "Сразу.")
        elapsed = time.monotonic() - started_at

        release_reaction.set()
        background.join(timeout=1)
        self.assertLess(elapsed, 0.5)
        self.assertFalse(background.is_alive())

    def test_delivered_companion_line_is_sent_once_with_next_chat(self) -> None:
        payloads = []

        def handler(request: httpx.Request) -> httpx.Response:
            payloads.append(__import__("json").loads(request.content))
            return httpx.Response(
                200,
                json={"answer": "Продолжим.", "session_id": 12},
            )

        client = self.make_client(handler)
        client.mark_companion_line_delivered("Ты надолго\nв игру?")

        client.send_message("На пару каток.")
        client.send_message("А ты как думаешь?")

        self.assertEqual(
            payloads[0]["preceding_assistant_lines"],
            ["Ты надолго в игру?"],
        )
        self.assertEqual(payloads[1]["preceding_assistant_lines"], [])


if __name__ == "__main__":
    unittest.main()
