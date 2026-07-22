import unittest

from app.api.desktop_auth import (
    DesktopAuthenticationError,
    desktop_authorization_headers,
    normalize_desktop_token,
)


class DesktopAuthTests(unittest.TestCase):
    def test_token_is_trimmed_before_use(self) -> None:
        self.assertEqual(normalize_desktop_token("  secret  "), "secret")
        self.assertEqual(
            desktop_authorization_headers("  secret  "),
            {"Authorization": "Bearer secret"},
        )

    def test_missing_token_is_rejected(self) -> None:
        for token in (None, "", "   "):
            with self.subTest(token=token):
                with self.assertRaises(DesktopAuthenticationError):
                    desktop_authorization_headers(token)


if __name__ == "__main__":
    unittest.main()
