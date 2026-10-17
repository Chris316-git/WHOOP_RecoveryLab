"""Database schema. Every table carries user_id so the same schema serves one user or many."""
from datetime import date, datetime, time

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# JSONB on Postgres; plain JSON on SQLite so the schema also runs in in-memory tests.
JSONB = PG_JSONB().with_variant(JSON(), "sqlite")


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # WHOOP user id
    first_name: Mapped[str | None] = mapped_column(String(100))
    timezone: Mapped[str | None] = mapped_column(String(64))  # IANA name, from Google Calendar
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ---------------- WHOOP ----------------

class Cycle(Base):
    """A physiological day: from waking up to the next wake-up."""
    __tablename__ = "whoop_cycles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), index=True)
    start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timezone_offset: Mapped[str | None] = mapped_column(String(10))
    score_state: Mapped[str | None] = mapped_column(String(32))
    strain: Mapped[float | None] = mapped_column(Float)
    kilojoule: Mapped[float | None] = mapped_column(Float)
    average_heart_rate: Mapped[int | None] = mapped_column(Integer)
    max_heart_rate: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw: Mapped[dict] = mapped_column(JSONB)


class Recovery(Base):
    __tablename__ = "whoop_recoveries"

    cycle_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), index=True)
    sleep_id: Mapped[str | None] = mapped_column(String(64))
    score_state: Mapped[str | None] = mapped_column(String(32))
    user_calibrating: Mapped[bool | None] = mapped_column(Boolean)
    recovery_score: Mapped[float | None] = mapped_column(Float)
    resting_heart_rate: Mapped[float | None] = mapped_column(Float)
    hrv_rmssd_milli: Mapped[float | None] = mapped_column(Float)
    spo2_percentage: Mapped[float | None] = mapped_column(Float)
    skin_temp_celsius: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw: Mapped[dict] = mapped_column(JSONB)


class Sleep(Base):
    __tablename__ = "whoop_sleeps"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # UUID in API v2
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), index=True)
    cycle_id: Mapped[int | None] = mapped_column(BigInteger)
    start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timezone_offset: Mapped[str | None] = mapped_column(String(10))
    nap: Mapped[bool | None] = mapped_column(Boolean)
    score_state: Mapped[str | None] = mapped_column(String(32))
    in_bed_min: Mapped[float | None] = mapped_column(Float)
    awake_min: Mapped[float | None] = mapped_column(Float)
    light_min: Mapped[float | None] = mapped_column(Float)
    deep_min: Mapped[float | None] = mapped_column(Float)  # slow-wave sleep
    rem_min: Mapped[float | None] = mapped_column(Float)
    disturbance_count: Mapped[int | None] = mapped_column(Integer)
    respiratory_rate: Mapped[float | None] = mapped_column(Float)
    sleep_performance_pct: Mapped[float | None] = mapped_column(Float)
    sleep_consistency_pct: Mapped[float | None] = mapped_column(Float)
    sleep_efficiency_pct: Mapped[float | None] = mapped_column(Float)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw: Mapped[dict] = mapped_column(JSONB)


class Workout(Base):
    __tablename__ = "whoop_workouts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # UUID in API v2
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), index=True)
    start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timezone_offset: Mapped[str | None] = mapped_column(String(10))
    sport_name: Mapped[str | None] = mapped_column(String(100))
    score_state: Mapped[str | None] = mapped_column(String(32))
    strain: Mapped[float | None] = mapped_column(Float)
    average_heart_rate: Mapped[int | None] = mapped_column(Integer)
    max_heart_rate: Mapped[int | None] = mapped_column(Integer)
    kilojoule: Mapped[float | None] = mapped_column(Float)
    distance_meter: Mapped[float | None] = mapped_column(Float)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw: Mapped[dict] = mapped_column(JSONB)


# ---------------- Calendar (time blocks only, no titles or attendee identities) ----------------

class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    event_key: Mapped[str] = mapped_column(String(300), primary_key=True)  # hashed calendar + event id
    start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    all_day: Mapped[bool] = mapped_column(Boolean, default=False)
    is_busy: Mapped[bool] = mapped_column(Boolean, default=True)
    attendee_count: Mapped[int] = mapped_column(Integer, default=0)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DailyCalendarFeatures(Base):
    __tablename__ = "daily_calendar_features"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    event_count: Mapped[int] = mapped_column(Integer)
    busy_minutes: Mapped[float] = mapped_column(Float)
    meeting_minutes: Mapped[float] = mapped_column(Float)  # busy events with 2+ attendees
    first_start_min: Mapped[int | None] = mapped_column(Integer)  # minutes after local midnight
    last_end_min: Mapped[int | None] = mapped_column(Integer)
    longest_free_block_min: Mapped[float] = mapped_column(Float)  # within the active window
    back_to_back_count: Mapped[int] = mapped_column(Integer)
    is_weekend: Mapped[bool] = mapped_column(Boolean)


# ---------------- Credentials ----------------

class OAuthToken(Base):
    """Encrypted OAuth credentials, one row per user and provider ("whoop", "google")."""
    __tablename__ = "oauth_tokens"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), primary_key=True)
    ciphertext: Mapped[str] = mapped_column(Text)  # Fernet-encrypted JSON
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UserSettings(Base):
    """Per-user preferences. Missing row = defaults (see src/report/schedule.py)."""
    __tablename__ = "user_settings"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    report_time: Mapped[time | None] = mapped_column(Time)        # earliest local send time
    latest_time: Mapped[time | None] = mapped_column(Time)        # send by then even if sleep is unscored
    wait_for_sleep: Mapped[bool | None] = mapped_column(Boolean)  # wait until last night is scored
    report_enabled: Mapped[bool | None] = mapped_column(Boolean)
    timezone: Mapped[str | None] = mapped_column(String(64))      # IANA name; None = follow the calendar
    rl_calendar_id: Mapped[str | None] = mapped_column(String(255))  # the app's own Google calendar
    sports: Mapped[str | None] = mapped_column(String(255))       # activities to suggest, comma-separated
    last_report_on: Mapped[date | None] = mapped_column(Date)     # local date of the last sent report
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ---------------- Planner ----------------

class DailyPlan(Base):
    """The focus chosen for a day and what came of it. Three things are kept apart, because
    the experiment engine needs to tell them apart:

    * the recommendation (focus, reasons, suggested block),
    * the user's response: None means no response at all, which is NOT a rejection;
      "added" (put it on the calendar), "dismissed", or "not_useful" (dismissed and said
      the suggestion itself was off),
    * the calendar state (None | "scheduled" | "removed") and, separately, the outcome
      measured from wearable data the next morning (src/feedback/outcome.py). Scheduling
      something is not the same as doing it.
    """
    __tablename__ = "daily_plans"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)      # local date of the plan
    timezone: Mapped[str | None] = mapped_column(String(64))
    # recommendation
    focus: Mapped[str] = mapped_column(String(32))                 # e.g. lower_intensity, none
    title: Mapped[str | None] = mapped_column(String(120))         # shown title (the AI writes its own)
    engine: Mapped[str | None] = mapped_column(String(16))         # "ai" or "rules": who made the shown plan
    score: Mapped[float] = mapped_column(Float)
    reasons: Mapped[list] = mapped_column(JSONB, default=list)
    block: Mapped[dict | None] = mapped_column(JSONB)              # suggested time block, if any
    considered: Mapped[list] = mapped_column(JSONB, default=list)  # every candidate and its score
    # reasoning record, for evaluating the AI against the rule engine
    rule_focus: Mapped[dict | None] = mapped_column(JSONB)         # what the rule engine chose
    ai_output: Mapped[dict | None] = mapped_column(JSONB)          # the AI's raw structured answer
    ai_status: Mapped[str | None] = mapped_column(String(16))      # ok | rejected | error | off
    ai_problems: Mapped[list | None] = mapped_column(JSONB)        # why the validator rejected it
    evidence: Mapped[dict | None] = mapped_column(JSONB)           # the case file the AI saw
    # response
    response: Mapped[str | None] = mapped_column(String(16))       # None | added | dismissed | not_useful
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # calendar
    calendar_status: Mapped[str | None] = mapped_column(String(16))  # None | scheduled | removed
    final_block: Mapped[dict | None] = mapped_column(JSONB)        # the block actually put on the calendar
    calendar_id: Mapped[str | None] = mapped_column(String(255))
    event_id: Mapped[str | None] = mapped_column(String(255))      # Google event on the app's calendar
    # outcome, measured the next morning
    outcome: Mapped[str | None] = mapped_column(String(16))        # done | partly | not_done | no_data | unmeasured
    outcome_detail: Mapped[dict | None] = mapped_column(JSONB)
    outcome_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ---------------- Experiments (Phase 4, v0.1) ----------------

class Experiment(Base):
    """One personal experiment: a preset intervention, a randomized night-by-night schedule and,
    once finished, the analysis result. One active experiment per user at a time."""
    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), index=True)
    preset: Mapped[str] = mapped_column(String(48))
    start_day: Mapped[date] = mapped_column(Date)                  # first experiment night (local date)
    nights: Mapped[int] = mapped_column(Integer)
    seed: Mapped[int] = mapped_column(BigInteger)                  # makes the random schedule reproducible
    schedule: Mapped[list] = mapped_column(JSONB)                  # [{"day": "2026-10-18", "arm": "treatment"}, ...]
    status: Mapped[str] = mapped_column(String(16), default="active")
    # proposed (by the AI, waiting for Start) | declined | active | completed | stopped
    proposed_on: Mapped[date | None] = mapped_column(Date)         # set when the AI proposed it
    reason: Mapped[str | None] = mapped_column(Text)               # the AI's checked reason for proposing it
    next_step: Mapped[str | None] = mapped_column(String(16))      # keep | drop (extend reopens the experiment)
    extensions: Mapped[int | None] = mapped_column(Integer, default=0)
    result: Mapped[dict | None] = mapped_column(JSONB)             # analysis, written once at the end
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExperimentDay(Base):
    """What the user confirmed for one experiment night. No row (or None) = not answered."""
    __tablename__ = "experiment_days"

    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    adherence: Mapped[str | None] = mapped_column(String(8))       # yes | no
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
