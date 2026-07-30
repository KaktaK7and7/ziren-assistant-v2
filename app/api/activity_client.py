import httpx

from app.api.desktop_auth import (
    DesktopAuthenticationError,
    desktop_authorization_headers,
    normalize_desktop_token,
)
from app.config.settings import AUTH_SITE_URL, DESKTOP_TOKEN_ENV, get_desktop_token


class ActivityClient:
    def __init__(
        self,
        desktop_token: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
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
            timeout=10.0,
        )

    def record(
        self,
        event_type: str,
        feature_id: str,
        subject_label: str = "",
    ) -> dict:
        response = self.client.post(
            "/api/desktop/activity",
            headers=self.authorization_headers,
            json={
                "event_type": event_type,
                "feature_id": feature_id,
                "subject_label": subject_label[:120],
            },
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def record_command(self, feature_id: str, subject_label: str) -> dict:
        return self.record(
            event_type="command.completed",
            feature_id=feature_id,
            subject_label=subject_label,
        )
