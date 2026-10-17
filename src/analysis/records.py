"""The device-agnostic daily record: the contract between wearable adapters and analysis.

Day convention: `day` is the behavior day. Its sleep is the main sleep that starts on the
evening of `day`; its load is the activity accumulated during `day`. Every field except
`day` and `source` is optional, because devices measure different things.
"""
from dataclasses import asdict, dataclass, fields
from datetime import date, datetime


@dataclass
class DailyRecord:
    day: date
    source: str                                   # e.g. "whoop"

    # Sleep (night of `day`)
    total_sleep_min: float | None = None          # light + deep + REM
    deep_min: float | None = None                 # slow-wave sleep
    rem_min: float | None = None
    in_bed_min: float | None = None
    sleep_efficiency_pct: float | None = None
    sleep_performance_pct: float | None = None    # vendor score: share of sleep need achieved
    respiratory_rate: float | None = None         # breaths per minute
    sleep_start_local: datetime | None = None     # naive local time
    sleep_need_baseline_min: float | None = None  # vendor's personal baseline need, if provided
    sleep_need_total_min: float | None = None     # need incl. debt/strain adjustments, if provided
    tz_offset_min: int | None = None              # minutes east of UTC where the user slept

    # Morning after (readiness)
    recovery_score: float | None = None           # vendor readiness score, 0-100
    hrv_rmssd_milli: float | None = None          # HRV as RMSSD in milliseconds
    resting_heart_rate: float | None = None       # bpm
    calibrating: bool | None = None               # vendor still learning the baseline

    # Activity during `day`
    load: float | None = None                     # daily load on WHOOP's 0-21 strain scale

    source_sleep_id: str | None = None            # traceability back to the raw record

    def to_dict(self) -> dict:
        return asdict(self)


RECORD_FIELDS = [f.name for f in fields(DailyRecord)]
NUMERIC_FIELDS = [
    "total_sleep_min", "deep_min", "rem_min", "in_bed_min", "sleep_efficiency_pct",
    "sleep_performance_pct", "respiratory_rate", "sleep_need_baseline_min", "sleep_need_total_min",
    "tz_offset_min", "recovery_score", "hrv_rmssd_milli", "resting_heart_rate", "load",
]
