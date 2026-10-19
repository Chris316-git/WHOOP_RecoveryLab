"""Personal memory: what the user told Recovery Lab about their goals, preferences, constraints
and corrections. The daily agent and the coach read it; only the coach writes it, and only
things the user said. Forgetting keeps the row (inactive) so a forgotten item is never
re-learned silently; `delete_all` removes everything."""
from datetime import datetime, timezone

from sqlalchemy import select

from src.db.models import UserMemory

KINDS = ("goal", "preference", "constraint", "correction")
MAX_ACTIVE = 30
MAX_CHARS = 240


def clean(kind: str, text: str) -> tuple[str, str] | None:
    text = " ".join(str(text or "").split())
    if kind not in KINDS or not 3 <= len(text) <= MAX_CHARS:
        return None
    return kind, text


def active(session, user_id: int) -> list[dict]:
    rows = session.scalars(select(UserMemory).where(UserMemory.user_id == user_id, UserMemory.active.is_(True))
                           .order_by(UserMemory.id))
    return [dict(id=m.id, kind=m.kind, text=m.text, since=m.created_at.date().isoformat() if m.created_at else None)
            for m in rows]


def add(session, user_id: int, kind: str, text: str, source: str = "coach") -> dict | None:
    c = clean(kind, text)
    if c is None:
        return None
    existing = active(session, user_id)
    same = next((m for m in existing if m["text"].lower() == c[1].lower()), None)
    if same:
        return same
    if len(existing) >= MAX_ACTIVE:
        return None
    m = UserMemory(user_id=user_id, kind=c[0], text=c[1], source=source, active=True)
    session.add(m)
    session.commit()
    return dict(id=m.id, kind=m.kind, text=m.text)


def forget(session, user_id: int, memory_id: int) -> bool:
    m = session.get(UserMemory, memory_id)
    if m is None or m.user_id != user_id or not m.active:
        return False
    m.active, m.forgotten_at = False, datetime.now(timezone.utc)
    session.commit()
    return True


def delete_all(session, user_id: int) -> int:
    rows = list(session.scalars(select(UserMemory).where(UserMemory.user_id == user_id)))
    for m in rows:
        session.delete(m)
    session.commit()
    return len(rows)
