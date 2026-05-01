import httpx

from app.config.settings import AI_SERVICE_URL


class NeuroClient:
    def __init__(self, user_id: int, session_id: int | None = None) -> None:
        self.user_id = user_id
        self.session_id = session_id

        self.client = httpx.Client(
            base_url=AI_SERVICE_URL,
            timeout=30.0,
        )

    def send_message(self, message: str) -> str:
        response = self.client.post(
            "/chat",
            json={
                "user_id": self.user_id,
                "message": message,
                "session_id": self.session_id,
            },
        )

        response.raise_for_status()
        data = response.json()

        self.session_id = data.get("session_id", self.session_id)

        return data.get("answer", "")