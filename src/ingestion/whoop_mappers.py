"""Pure functions that turn WHOOP API payloads into table rows. No I/O, easy to unit test."""
from datetime import datetime

MS_PER_MIN = 60_000


def parse_ts(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def ms_to_min(ms: float | None) -> float | None:
    return round(ms / MS_PER_MIN, 1) if ms is not None else None


def cycle_row(r: dict) -> dict:
    s = r.get("score") or {}
    return dict(
        id=r["id"], user_id=r["user_id"],
        start=parse_ts(r.get("start")), end=parse_ts(r.get("end")),
        timezone_offset=r.get("timezone_offset"), score_state=r.get("score_state"),
        strain=s.get("strain"), kilojoule=s.get("kilojoule"),
        average_heart_rate=s.get("average_heart_rate"), max_heart_rate=s.get("max_heart_rate"),
        updated_at=parse_ts(r.get("updated_at")), raw=r,
    )


def recovery_row(r: dict) -> dict:
    s = r.get("score") or {}
    return dict(
        cycle_id=r["cycle_id"], user_id=r["user_id"], sleep_id=r.get("sleep_id"),
        score_state=r.get("score_state"), user_calibrating=s.get("user_calibrating"),
        recovery_score=s.get("recovery_score"), resting_heart_rate=s.get("resting_heart_rate"),
        hrv_rmssd_milli=s.get("hrv_rmssd_milli"), spo2_percentage=s.get("spo2_percentage"),
        skin_temp_celsius=s.get("skin_temp_celsius"),
        created_at=parse_ts(r.get("created_at")), updated_at=parse_ts(r.get("updated_at")), raw=r,
    )


def sleep_row(r: dict) -> dict:
    s = r.get("score") or {}
    st = s.get("stage_summary") or {}
    return dict(
        id=str(r["id"]), user_id=r["user_id"], cycle_id=r.get("cycle_id"),
        start=parse_ts(r.get("start")), end=parse_ts(r.get("end")),
        timezone_offset=r.get("timezone_offset"), nap=r.get("nap"), score_state=r.get("score_state"),
        in_bed_min=ms_to_min(st.get("total_in_bed_time_milli")),
        awake_min=ms_to_min(st.get("total_awake_time_milli")),
        light_min=ms_to_min(st.get("total_light_sleep_time_milli")),
        deep_min=ms_to_min(st.get("total_slow_wave_sleep_time_milli")),
        rem_min=ms_to_min(st.get("total_rem_sleep_time_milli")),
        disturbance_count=st.get("disturbance_count"),
        respiratory_rate=s.get("respiratory_rate"),
        sleep_performance_pct=s.get("sleep_performance_percentage"),
        sleep_consistency_pct=s.get("sleep_consistency_percentage"),
        sleep_efficiency_pct=s.get("sleep_efficiency_percentage"),
        updated_at=parse_ts(r.get("updated_at")), raw=r,
    )


def workout_row(r: dict) -> dict:
    s = r.get("score") or {}
    return dict(
        id=str(r["id"]), user_id=r["user_id"],
        start=parse_ts(r.get("start")), end=parse_ts(r.get("end")),
        timezone_offset=r.get("timezone_offset"), sport_name=r.get("sport_name"),
        score_state=r.get("score_state"), strain=s.get("strain"),
        average_heart_rate=s.get("average_heart_rate"), max_heart_rate=s.get("max_heart_rate"),
        kilojoule=s.get("kilojoule"), distance_meter=s.get("distance_meter"),
        updated_at=parse_ts(r.get("updated_at")), raw=r,
    )
