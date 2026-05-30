import os

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv()

AUTH_SITE_URL = os.getenv("AUTH_SITE_URL", "http://localhost:3000").rstrip("/")
AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://localhost:8000").rstrip("/")
APP_NAME = "Ziren Assistant v2"
