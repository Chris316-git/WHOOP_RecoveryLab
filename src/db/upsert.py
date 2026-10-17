"""Generic upsert (INSERT ... ON CONFLICT DO UPDATE) for Postgres, with SQLite support for tests."""
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session


def upsert(session: Session, model, rows: list[dict], keys: list[str]) -> int:
    if not rows:
        return 0
    # Postgres rejects an upsert that touches the same key twice in one statement.
    rows = list({tuple(row[k] for k in keys): row for row in rows}.values())
    insert = sqlite.insert if session.get_bind().dialect.name == "sqlite" else postgresql.insert
    stmt = insert(model).values(rows)
    update_cols = {c: stmt.excluded[c] for c in rows[0] if c not in keys}
    if update_cols:
        stmt = stmt.on_conflict_do_update(index_elements=keys, set_=update_cols)
    else:
        stmt = stmt.on_conflict_do_nothing(index_elements=keys)
    session.execute(stmt)
    return len(rows)
