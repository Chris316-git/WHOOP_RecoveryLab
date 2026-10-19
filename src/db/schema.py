"""Create missing tables and apply small additive column changes. Idempotent.

`create_all` creates new tables but never alters existing ones, so columns added to a
table after it was created are listed here. (A migration tool such as Alembic can take
over once the schema changes more often.)
"""
from sqlalchemy import inspect, text

from src.db.models import Base

ADDED_COLUMNS = [
    ("user_settings", "timezone", "VARCHAR(64)"),
    ("user_settings", "rl_calendar_id", "VARCHAR(255)"),
    ("user_settings", "sports", "VARCHAR(255)"),
    ("daily_plans", "timezone", "VARCHAR(64)"),
    ("daily_plans", "final_block", "JSONB"),
    ("daily_plans", "event_id", "VARCHAR(255)"),
    ("daily_plans", "decided_at", "TIMESTAMPTZ"),
    ("daily_plans", "response", "VARCHAR(16)"),
    ("daily_plans", "calendar_status", "VARCHAR(16)"),
    ("daily_plans", "calendar_id", "VARCHAR(255)"),
    ("daily_plans", "outcome", "VARCHAR(16)"),
    ("daily_plans", "outcome_detail", "JSONB"),
    ("daily_plans", "outcome_checked_at", "TIMESTAMPTZ"),
    ("daily_plans", "title", "VARCHAR(120)"),
    ("daily_plans", "engine", "VARCHAR(16)"),
    ("daily_plans", "rule_focus", "JSONB"),
    ("daily_plans", "ai_output", "JSONB"),
    ("daily_plans", "ai_status", "VARCHAR(16)"),
    ("daily_plans", "ai_problems", "JSONB"),
    ("daily_plans", "evidence", "JSONB"),
    ("daily_plans", "agent_notes", "JSONB"),
    ("daily_plans", "agent_trace", "JSONB"),
    ("experiments", "proposed_on", "DATE"),
    ("experiments", "reason", "TEXT"),
    ("experiments", "next_step", "VARCHAR(16)"),
    ("experiments", "extensions", "INTEGER"),
]

# daily_plans.status (proposed|accepted|adjusted|declined) was split into response and
# calendar_status. Old rows are carried over once, and the old column stops being required.
LEGACY_STATUS = [
    "UPDATE daily_plans SET response = 'added', calendar_status = CASE WHEN event_id IS NOT NULL "
    "THEN 'scheduled' END WHERE status IN ('accepted', 'adjusted') AND response IS NULL",
    "UPDATE daily_plans SET response = 'dismissed' WHERE status = 'declined' AND response IS NULL",
    "ALTER TABLE daily_plans ALTER COLUMN status DROP NOT NULL",
]


def ensure_schema(engine) -> None:
    Base.metadata.create_all(engine)
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        for table, column, sql_type in ADDED_COLUMNS:
            conn.execute(text(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS "{column}" {sql_type}'))
        if "status" in {c["name"] for c in inspect(conn).get_columns("daily_plans")}:
            for statement in LEGACY_STATUS:
                conn.execute(text(statement))
