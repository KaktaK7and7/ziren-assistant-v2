import threading

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
        self._session_lock = threading.Lock()
        self._chat_lock = threading.Lock()
        self._delivered_companion_lines: list[str] = []

    def _get_session_id(self) -> int | None:
        with self._session_lock:
            return self.session_id

    def _update_session_id(
        self,
        request_session_id: int | None,
        response_session_id: object,
    ) -> None:
        if not isinstance(response_session_id, int):
            return

        with self._session_lock:
            if request_session_id is None and self.session_id is not None:
                return

            self.session_id = response_session_id

    def mark_companion_line_delivered(self, line: str) -> None:
        safe_line = "".join(
            character
            if character >= " " and character != "\x7f"
            else " "
            for character in str(line or "")
        )
        normalized = " ".join(safe_line.split())[:600]

        if not normalized:
            return

        with self._session_lock:
            self._delivered_companion_lines.append(normalized)
            self._delivered_companion_lines = (
                self._delivered_companion_lines[-2:]
            )

    def _get_chat_context(self) -> tuple[int | None, list[str]]:
        with self._session_lock:
            return (
                self.session_id,
                list(self._delivered_companion_lines),
            )

    def _forget_delivered_lines(self, delivered_lines: list[str]) -> None:
        if not delivered_lines:
            return

        with self._session_lock:
            for delivered_line in delivered_lines:
                try:
                    self._delivered_companion_lines.remove(delivered_line)
                except ValueError:
                    continue

    def _post(self, path: str, payload: dict) -> dict:
        request_session_id = payload.get("session_id")
        response = self.client.post(
            path,
            headers=self.authorization_headers,
            json=payload,
        )

        if response.status_code in (401, 403):
            raise NeuroAuthenticationError(
                "Desktop session is no longer authorized"
            )

        response.raise_for_status()
        data = response.json()

        if isinstance(data, dict):
            self._update_session_id(
                request_session_id,
                data.get("session_id"),
            )
            return data

        return {}

    def send_message(
        self,
        message: str,
        capabilities: list[dict] | None = None,
    ) -> str:
        with self._chat_lock:
            session_id, delivered_lines = self._get_chat_context()
            data = self._post(
                "/api/assistant/chat",
                {
                    "message": message,
                    "session_id": session_id,
                    "preceding_assistant_lines": delivered_lines,
                    "capabilities": capabilities or [],
                },
            )
            self._forget_delivered_lines(delivered_lines)

        return str(data.get("answer", ""))

    def request_command_reaction(
        self,
        feature_id: str,
        subject_label: str,
        result_text: str,
        capabilities: list[dict] | None = None,
    ) -> str:
        data = self._post(
            "/api/assistant/reaction",
            {
                "feature_id": feature_id,
                "subject_label": subject_label,
                "result_text": result_text,
                "session_id": self._get_session_id(),
                "capabilities": capabilities or [],
            },
        )
        return str(data.get("text", ""))

    def request_proactive(
        self,
        idle_minutes: int,
        capabilities: list[dict] | None = None,
    ) -> str:
        data = self._post(
            "/api/assistant/proactive",
            {
                "idle_minutes": idle_minutes,
                "session_id": self._get_session_id(),
                "capabilities": capabilities or [],
            },
        )
        return str(data.get("text", ""))
