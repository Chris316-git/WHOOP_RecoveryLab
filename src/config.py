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

# Where OAuth credentials live: "file" (.tokens/, local development) or "db" (encrypted in
# the oauth_tokens table; required for the scheduled cloud job). Use ONE store everywhere:
# WHOOP rotates refresh tokens, so two stores would keep invalidating each other.
TOKEN_STORE = os.getenv("TOKEN_STORE", "file").strip().lower()
TOKEN_DIR = PROJECT_ROOT / ".tokens"
WHOOP_TOKEN_DIR = TOKEN_DIR / "whoop"
GOOGLE_TOKEN_DIR = TOKEN_DIR / "google"

# Daily report
REPORT_TIMEZONE = os.getenv("REPORT_TIMEZONE", "America/Los_Angeles")  # fallback if the calendar has none
REPORT_EMAIL_TO = os.getenv("REPORT_EMAIL_TO", "")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
REPORT_DIR = PROJECT_ROOT / "data" / "reports"  # local previews (git-ignored)
