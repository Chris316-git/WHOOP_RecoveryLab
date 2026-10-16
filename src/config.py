"""Central configuration loaded from environment variables."""
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}. Check your .env file.")
    return value


# WHOOP
WHOOP_REDIRECT_URI = os.getenv("WHOOP_REDIRECT_URI", "http://localhost:8000/callback")
WHOOP_AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
WHOOP_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
WHOOP_API_BASE = "https://api.prod.whoop.com/developer/v2"
WHOOP_SCOPES = [
    "offline",
    "read:recovery",
    "read:cycles",
    "read:sleep",
    "read:workout",
    "read:profile",
    "read:body_measurement",
]

# Google Calendar
GOOGLE_CLIENT_SECRET_FILE = PROJECT_ROOT / os.getenv(
    "GOOGLE_CLIENT_SECRET_FILE", "secrets/google_client_secret.json"
)
GOOGLE_CALENDAR_IDS = [c.strip() for c in os.getenv("GOOGLE_CALENDAR_IDS", "primary").split(",") if c.strip()]
GOOGLE_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

# Local credential storage for development (replaced by an encrypted DB table for multi-user).
TOKEN_DIR = PROJECT_ROOT / ".tokens"
WHOOP_TOKEN_DIR = TOKEN_DIR / "whoop"
GOOGLE_TOKEN_DIR = TOKEN_DIR / "google"
