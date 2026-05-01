import httpx

from app.config.settings import AUTH_SITE_URL
from app.storage.local_store import load_session, save_session, clear_session


class AuthClient:
    def __init__(self) -> None:
        self.client = httpx.Client(
            base_url=AUTH_SITE_URL,
            follow_redirects=True,
            timeout=15.0,
        )

    def login(self, email: str, password: str) -> dict:
        response = self.client.post(
            "/login",
            data={
                "email": email,
                "password": password,
            },
        )

        response.raise_for_status()

        me = self.get_current_user()

        if not me.get("loggedIn"):
            raise RuntimeError("Не удалось войти в аккаунт. Проверь email и пароль.")

        user = me["user"]

        session_data = {
            "user_id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "session_id": None,
        }

        save_session(session_data)
        return session_data

    def get_current_user(self) -> dict:
        response = self.client.get("/api/me")
        response.raise_for_status()
        return response.json()

    def get_saved_session(self) -> dict:
        return load_session()

    def logout(self) -> None:
        try:
            self.client.get("/logout")
        except Exception:
            pass

        clear_session()