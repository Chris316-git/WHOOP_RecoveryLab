"""Database schema. Every table carries user_id so the same schema serves one user or many."""
from datetime import date, datetime, time

from sqlalchemy import (
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


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
    last_report_on: Mapped[date | None] = mapped_column(Date)     # local date of the last sent report
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
