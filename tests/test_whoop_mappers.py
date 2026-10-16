from src.ingestion.whoop_mappers import recovery_row, sleep_row


def test_recovery_row_extracts_scores():
    payload = {
        "cycle_id": 93845, "user_id": 10129, "sleep_id": "abc", "score_state": "SCORED",
        "created_at": "2026-10-01T11:25:44.774Z", "updated_at": "2026-10-01T14:25:44.774Z",
        "score": {"recovery_score": 44, "resting_heart_rate": 64, "hrv_rmssd_milli": 31.8},
    }
    row = recovery_row(payload)
    assert row["recovery_score"] == 44
    assert row["hrv_rmssd_milli"] == 31.8
    assert row["created_at"].tzinfo is not None
    assert row["raw"] is payload


def test_sleep_row_converts_ms_to_minutes_and_handles_unscored():
    payload = {
        "id": "uuid-1", "user_id": 1, "start": "2026-10-01T06:00:00Z", "end": "2026-10-01T14:00:00Z",
        "score": {"stage_summary": {"total_slow_wave_sleep_time_milli": 5_400_000}},
    }
    assert sleep_row(payload)["deep_min"] == 90.0
    unscored = {"id": "uuid-2", "user_id": 1, "start": "2026-10-02T06:00:00Z", "score_state": "PENDING_SCORE"}
    assert sleep_row(unscored)["deep_min"] is None
