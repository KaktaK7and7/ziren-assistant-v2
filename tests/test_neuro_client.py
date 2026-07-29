import unittest

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
            return httpx.Response(
                200,
                json={"answer": "Я здесь.", "session_id": 7},
            )

        client = self.make_client(handler)

        self.assertEqual(client.send_message("ты тут"), "Я здесь.")
        self.assertEqual(client.session_id, 7)

    def test_reports_expired_desktop_session_separately(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "Not authenticated"})

        client = self.make_client(handler)

        with self.assertRaises(NeuroAuthenticationError):
            client.send_message("ты тут")


if __name__ == "__main__":
    unittest.main()
