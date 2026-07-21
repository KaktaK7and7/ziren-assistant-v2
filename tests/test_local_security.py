import unittest

from app.api.local_security import (
    DEFAULT_LOCAL_API_ORIGINS,
    get_local_auth_error,
    is_allowed_local_origin,
)


class LocalSecurityTests(unittest.TestCase):
    def test_known_tauri_and_dev_origins_are_allowed(self) -> None:
        for origin in DEFAULT_LOCAL_API_ORIGINS:
            with self.subTest(origin=origin):
                self.assertTrue(is_allowed_local_origin(origin))

        self.assertTrue(is_allowed_local_origin(None))
        self.assertFalse(is_allowed_local_origin("https://attacker.example"))

    def test_request_requires_exact_process_token(self) -> None:
        self.assertIsNone(
            get_local_auth_error("tauri://localhost", "secret", "secret")
        )
        self.assertEqual(
            get_local_auth_error("tauri://localhost", "wrong", "secret"),
            (401, "Invalid local API token"),
        )
        self.assertEqual(
            get_local_auth_error("tauri://localhost", "чужой", "secret"),
            (401, "Invalid local API token"),
        )

    def test_origin_is_checked_before_token(self) -> None:
        self.assertEqual(
            get_local_auth_error("https://attacker.example", "secret", "secret"),
            (403, "Origin is not allowed"),
        )

    def test_missing_server_token_fails_closed(self) -> None:
        self.assertEqual(
            get_local_auth_error(None, "secret", ""),
            (503, "Local API token is not configured"),
        )


if __name__ == "__main__":
    unittest.main()
