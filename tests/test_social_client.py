import base64
import unittest

import httpx

from app.api.social_client import (
    SocialApiError,
    SocialClient,
    SocialFriend,
    resolve_friend_by_voice,
)
from app.modules.system.social_messaging_module import SystemSocialMessagingModule


class FriendVoiceResolverTests(unittest.TestCase):
    def test_resolves_private_alias_in_russian_dative_form(self) -> None:
        friends = [
            SocialFriend(
                id=7,
                username="Diana_77",
                voice_alias="Диана",
            )
        ]

        resolved = resolve_friend_by_voice(friends, "диане")

        self.assertEqual(resolved.id, 7)

    def test_alias_has_priority_over_username_fuzzy_match(self) -> None:
        friends = [
            SocialFriend(id=1, username="Diana", voice_alias="Сестра"),
            SocialFriend(id=2, username="SisterDiana", voice_alias="Диана"),
        ]

        resolved = resolve_friend_by_voice(friends, "диане")

        self.assertEqual(resolved.id, 2)

    def test_unknown_friend_is_not_guessed(self) -> None:
        friends = [SocialFriend(id=1, username="Diana", voice_alias="Диана")]

        with self.assertRaises(SocialApiError):
            resolve_friend_by_voice(friends, "Алексей")


class SocialScreenshotTransportTests(unittest.TestCase):
    def test_screenshot_uses_binary_jpeg_route_instead_of_large_json(self) -> None:
        jpeg = b"\xff\xd8\xff\xe0ziren-test-jpeg"
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["path"] = request.url.path
            seen["recipient"] = request.url.params.get("recipient_id")
            seen["content_type"] = request.headers.get("content-type")
            seen["authorization"] = request.headers.get("authorization")
            seen["body"] = request.content
            return httpx.Response(
                201,
                json={
                    "ok": True,
                    "message": {
                        "id": 10,
                        "sender_id": 1,
                        "recipient_id": 7,
                        "kind": "screenshot",
                        "body": "",
                        "created_at": "2026-08-08T10:00:00Z",
                        "attachment_url": "/api/social/messages/10/attachment",
                    },
                },
            )

        http_client = httpx.Client(
            base_url="https://ziren.test",
            transport=httpx.MockTransport(handler),
        )
        client = SocialClient(desktop_token="desktop-test-token", client=http_client)
        friend = SocialFriend(id=7, username="Diana", voice_alias="Диана")
        data_url = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")

        message = client.send_screenshot(friend, data_url)

        self.assertEqual(seen["path"], "/api/social/screenshots")
        self.assertEqual(seen["recipient"], "7")
        self.assertEqual(seen["content_type"], "image/jpeg")
        self.assertEqual(seen["authorization"], "Bearer desktop-test-token")
        self.assertEqual(seen["body"], jpeg)
        self.assertEqual(message.kind, "screenshot")
        self.assertEqual(message.recipient_id, 7)


class FakeSocialClient:
    def __init__(self) -> None:
        self.friend = SocialFriend(id=7, username="Diana_77", voice_alias="Диана")
        self.sent = []

    def resolve_friend(self, spoken_name: str):
        if spoken_name.lower().strip() in {"диана", "диане"}:
            return self.friend
        raise SocialApiError("not found")

    def send_text(self, friend, body, *, kind="text"):
        self.sent.append((friend.id, body, kind))
        return None


class SocialMessagingCommandTests(unittest.TestCase):
    def test_voice_message_extracts_recipient_and_body(self) -> None:
        client = FakeSocialClient()
        module = SystemSocialMessagingModule(
            client=client,
            start_inbox_listener=False,
        )

        response = module.handle("напиши диане привет как дела")

        self.assertEqual(client.sent, [(7, "привет как дела", "text")])
        self.assertIn("Диана", response.text)

    def test_message_without_body_is_rejected(self) -> None:
        client = FakeSocialClient()
        module = SystemSocialMessagingModule(
            client=client,
            start_inbox_listener=False,
        )

        response = module.handle("напиши диане")

        self.assertFalse(client.sent)
        self.assertTrue(response.text)


if __name__ == "__main__":
    unittest.main()
