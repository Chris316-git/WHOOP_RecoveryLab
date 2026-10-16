"""WHOOP token storage keyed by user, so the same interface works for one user or many.

FileTokenStore keeps tokens in .tokens/ for local development. DbTokenStore keeps them
encrypted in Postgres so a scheduled cloud job can use them. Pick one with TOKEN_STORE.
"""
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from src import config


@dataclass
class WhoopToken:
    access_token: str
    refresh_token: str
    expires_at: float  # Unix timestamp
    scope: str = ""

    @classmethod
    def from_response(cls, data: dict) -> "WhoopToken":
        return cls(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            # Refresh one minute early to avoid using a token right as it expires.
            expires_at=time.time() + int(data.get("expires_in", 3600)) - 60,
            scope=data.get("scope", ""),
        )

    @property
    def is_expired(self) -> bool:
        return time.time() >= self.expires_at


class FileTokenStore:
    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, user_id: str) -> Path:
        return self.directory / f"{user_id}.json"

    def save(self, user_id: str, token: WhoopToken) -> None:
        path = self._path(user_id)
        path.write_text(json.dumps(asdict(token), indent=2))
        os.chmod(path, 0o600)  # readable only by the current OS user

    def load(self, user_id: str) -> WhoopToken:
        path = self._path(user_id)
        if not path.exists():
            raise FileNotFoundError(f"No WHOOP token for user {user_id}. Run the login flow first.")
        return WhoopToken(**json.loads(path.read_text()))

    def list_users(self) -> list[str]:
        return sorted(p.stem for p in self.directory.glob("*.json"))


class DbTokenStore:
    """Same interface as FileTokenStore, backed by the encrypted oauth_tokens table."""

    def __init__(self):
        from src.db.credentials import DbCredentialStore
        self._db = DbCredentialStore("whoop")

    def save(self, user_id: str, token: WhoopToken) -> None:
        self._db.save_json(user_id, json.dumps(asdict(token)))

    def load(self, user_id: str) -> WhoopToken:
        data = self._db.load_json(user_id)
        if data is None:
            raise FileNotFoundError(f"No WHOOP token for user {user_id} in the database.")
        return WhoopToken(**json.loads(data))

    def list_users(self) -> list[str]:
        return self._db.list_users()


def get_whoop_store():
    if config.TOKEN_STORE == "db":
        return DbTokenStore()
    if config.TOKEN_STORE == "file":
        return FileTokenStore(config.WHOOP_TOKEN_DIR)
    raise RuntimeError('TOKEN_STORE must be "file" or "db"')
