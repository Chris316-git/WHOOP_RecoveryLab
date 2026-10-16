"""Create missing tables and apply small additive column changes. Idempotent.

`create_all` creates new tables but never alters existing ones, so columns added to a
table after it was created are listed here. (A migration tool such as Alembic can take
over once the schema changes more often.)
"""
from sqlalchemy import text

from src.db.models import Base

ADDED_COLUMNS = [
    ("user_settings", "timezone", "VARCHAR(64)"),
]


def ensure_schema(engine) -> None:
    Base.metadata.create_all(engine)
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        for table, column, sql_type in ADDED_COLUMNS:
            conn.execute(text(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS "{column}" {sql_type}'))
