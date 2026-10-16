"""Google Calendar OAuth (read-only). Credentials are stored per app user."""
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from src import config


def _token_path(user_id: str):
    config.GOOGLE_TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    return config.GOOGLE_TOKEN_DIR / f"{user_id}.json"


def authorize(user_id: str) -> Credentials:
    """Run the browser consent flow once and save the credentials."""
    if not config.GOOGLE_CLIENT_SECRET_FILE.exists():
        raise FileNotFoundError(
            f"Google OAuth client file not found at {config.GOOGLE_CLIENT_SECRET_FILE}. "
            "Download it from Google Cloud Console (OAuth client, Desktop app)."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(config.GOOGLE_CLIENT_SECRET_FILE), config.GOOGLE_SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    path = _token_path(user_id)
    path.write_text(creds.to_json())
    path.chmod(0o600)
    return creds


def load_credentials(user_id: str) -> Credentials:
    path = _token_path(user_id)
    if not path.exists():
        raise FileNotFoundError(f"No Google credentials for user {user_id}. Run `make connect-google` first.")
    creds = Credentials.from_authorized_user_file(str(path), config.GOOGLE_SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        path.write_text(creds.to_json())
    return creds
