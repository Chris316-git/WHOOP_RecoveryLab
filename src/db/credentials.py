"""Encrypted per-user credential storage in Postgres (table oauth_tokens)."""
from sqlalchemy import select

from src.db.models import OAuthToken, User
from src.db.upsert import upsert
from src.security import decrypt, encrypt


class DbCredentialStore:
    """Stores an opaque JSON string per (user, provider), encrypted at rest."""

    def __init__(self, provider: str):
        self.provider = provider

    @staticmethod
    def _session():
        from src.db.session import SessionLocal  # imported lazily: needs DATABASE_URL
        return SessionLocal()

    def save_json(self, user_id: str, data: str) -> None:
        # Committed immediately and in its own session: WHOOP invalidates the old refresh
        # token on every refresh, so the new one must never be lost to a later rollback.
        with self._session() as session:
            upsert(session, User, [{"user_id": int(user_id)}], ["user_id"])
            upsert(session, OAuthToken, [dict(user_id=int(user_id), provider=self.provider,
                                              ciphertext=encrypt(data))], ["user_id", "provider"])
            session.commit()

    def load_json(self, user_id: str) -> str | None:
        with self._session() as session:
            row = session.get(OAuthToken, (int(user_id), self.provider))
            return decrypt(row.ciphertext) if row else None

    def list_users(self) -> list[str]:
        with self._session() as session:
            ids = session.scalars(select(OAuthToken.user_id).where(OAuthToken.provider == self.provider))
            return sorted(str(i) for i in ids)
