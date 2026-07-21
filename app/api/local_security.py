import hmac


LOCAL_TOKEN_HEADER = "X-Ziren-Local-Token"
DEFAULT_LOCAL_API_ORIGINS = frozenset(
    {
        "tauri://localhost",
        "http://tauri.localhost",
        "https://tauri.localhost",
        "http://localhost:1420",
        "http://localhost:5173",
    }
)


def is_allowed_local_origin(origin: str | None) -> bool:
    normalized_origin = str(origin or "").strip()
    return not normalized_origin or normalized_origin in DEFAULT_LOCAL_API_ORIGINS


def get_local_auth_error(
    origin: str | None,
    provided_token: str | None,
    expected_token: str | None,
) -> tuple[int, str] | None:
    if not is_allowed_local_origin(origin):
        return 403, "Origin is not allowed"

    normalized_expected = str(expected_token or "").strip()

    if not normalized_expected:
        return 503, "Local API token is not configured"

    normalized_provided = str(provided_token or "")

    if not hmac.compare_digest(
        normalized_provided.encode("utf-8"),
        normalized_expected.encode("utf-8"),
    ):
        return 401, "Invalid local API token"

    return None
