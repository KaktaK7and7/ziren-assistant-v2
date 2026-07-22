import os

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv()

AUTH_SITE_URL = os.getenv("AUTH_SITE_URL", "http://localhost:3000").rstrip("/")
DESKTOP_TOKEN_ENV = "ZIREN_DESKTOP_TOKEN"
LOCAL_API_TOKEN_ENV = "ZIREN_LOCAL_API_TOKEN"
APP_NAME = "Ziren Assistant v2"


def get_desktop_token() -> str:
    return os.getenv(DESKTOP_TOKEN_ENV, "").strip()


def get_local_api_token() -> str:
    return os.getenv(LOCAL_API_TOKEN_ENV, "").strip()
