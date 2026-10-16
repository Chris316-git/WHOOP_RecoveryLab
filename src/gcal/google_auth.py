"""Google Calendar OAuth (read-only). Credentials are stored per app user, either in
.tokens/google/ or encrypted in the database, depending on TOKEN_STORE."""
import json

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from src import config


def _token_path(user_id: str):
    config.GOOGLE_TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    return config.GOOGLE_TOKEN_DIR / f"{user_id}.json"


def _db():
    from src.db.credentials import DbCredentialStore
    return DbCredentialStore("google")


def save_credentials(user_id: str, creds_json: str) -> None:
    if config.TOKEN_STORE == "db":
        _db().save_json(user_id, creds_json)
    else:
        path = _token_path(user_id)
        path.write_text(creds_json)
        path.chmod(0o600)


def _load_json(user_id: str) -> str | None:
    if config.TOKEN_STORE == "db":
        return _db().load_json(user_id)
    path = _token_path(user_id)
    return path.read_text() if path.exists() else None


def connected_users() -> list[str]:
    if config.TOKEN_STORE == "db":
        return _db().list_users()
    if not config.GOOGLE_TOKEN_DIR.exists():
        return []
    return sorted(p.stem for p in config.GOOGLE_TOKEN_DIR.glob("*.json"))


def authorize(user_id: str) -> Credentials:
    """Run the browser consent flow once and save the credentials."""
    if not config.GOOGLE_CLIENT_SECRET_FILE.exists():
        raise FileNotFoundError(
            f"Google OAuth client file not found at {config.GOOGLE_CLIENT_SECRET_FILE}. "
            "Download it from Google Cloud Console (OAuth client, Desktop app)."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(config.GOOGLE_CLIENT_SECRET_FILE), config.GOOGLE_SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    save_credentials(user_id, creds.to_json())
    return creds


def load_credentials(user_id: str) -> Credentials:
    """Stored credentials, refreshed if needed. They embed the OAuth client id/secret, so
    the cloud job does not need the client secret file."""
    data = _load_json(user_id)
    if data is None:
        raise FileNotFoundError(f"No Google credentials for user {user_id}. Run `make connect-google` first.")
    creds = Credentials.from_authorized_user_info(json.loads(data), config.GOOGLE_SCOPES)
    if not creds.valid and creds.refresh_token:
        creds.refresh(Request())
        save_credentials(user_id, creds.to_json())
    return creds
