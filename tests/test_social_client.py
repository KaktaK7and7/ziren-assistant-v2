import unittest

from app.api.social_client import (
    SocialApiError,
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
