import httpx

from app.api.desktop_auth import (
    DesktopAuthenticationError,
    desktop_authorization_headers,
    normalize_desktop_token,
)
from app.config.settings import AUTH_SITE_URL, DESKTOP_TOKEN_ENV, get_desktop_token


class AuthClient:
    def __init__(
        self,
        desktop_token: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.desktop_token = normalize_desktop_token(
            desktop_token or get_desktop_token()
        )
        self.client = client or httpx.Client(
            base_url=AUTH_SITE_URL,
            timeout=15.0,
        )

    def require_current_user(self) -> dict:
        try:
            headers = self.authorization_headers()
        except DesktopAuthenticationError as error:
            raise RuntimeError(f"{error} ({DESKTOP_TOKEN_ENV})") from error

        response = self.client.get(
            "/api/desktop/me",
            headers=headers,
        )
        response.raise_for_status()
        payload = response.json()
        user = payload.get("user")

        if not payload.get("ok") or not isinstance(user, dict) or not user.get("id"):
            raise RuntimeError("Desktop authorization session is invalid")

        return user

    def authorization_headers(self) -> dict[str, str]:
        return desktop_authorization_headers(self.desktop_token)
