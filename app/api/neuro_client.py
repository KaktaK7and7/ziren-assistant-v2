import httpx

from app.api.desktop_auth import (
    DesktopAuthenticationError,
    desktop_authorization_headers,
    normalize_desktop_token,
)
from app.config.settings import AUTH_SITE_URL, DESKTOP_TOKEN_ENV, get_desktop_token


class NeuroAuthenticationError(RuntimeError):
    """The desktop session is no longer accepted by the assistant gateway."""


class NeuroClient:
    def __init__(
        self,
        session_id: int | None = None,
        desktop_token: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.session_id = session_id
        self.desktop_token = normalize_desktop_token(
            desktop_token or get_desktop_token()
        )

        try:
            self.authorization_headers = desktop_authorization_headers(
                self.desktop_token
            )
        except DesktopAuthenticationError as error:
            raise RuntimeError(f"{error} ({DESKTOP_TOKEN_ENV})") from error

        self.client = client or httpx.Client(
            base_url=AUTH_SITE_URL,
            timeout=30.0,
        )

    def send_message(self, message: str) -> str:
        response = self.client.post(
            "/api/assistant/chat",
            headers=self.authorization_headers,
            json={
                "message": message,
                "session_id": self.session_id,
            },
        )

        if response.status_code in (401, 403):
            raise NeuroAuthenticationError(
                "Desktop session is no longer authorized"
            )

        response.raise_for_status()
        data = response.json()

        self.session_id = data.get("session_id", self.session_id)

        return data.get("answer", "")
