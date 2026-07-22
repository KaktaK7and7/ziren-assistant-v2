class DesktopAuthenticationError(RuntimeError):
    pass


def normalize_desktop_token(token: str | None) -> str:
    return str(token or "").strip()


def desktop_authorization_headers(token: str | None) -> dict[str, str]:
    normalized_token = normalize_desktop_token(token)

    if not normalized_token:
        raise DesktopAuthenticationError("Desktop authorization token is missing")

    return {"Authorization": f"Bearer {normalized_token}"}
