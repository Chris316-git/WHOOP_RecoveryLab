"""Wearable adapters. Each adapter turns one vendor's stored rows into device-agnostic
`DailyRecord`s (src/analysis/records.py); nothing downstream knows which device produced them.

Adding a device (e.g. Oura or Garmin) means writing one module here with a
`daily_records(...) -> list[DailyRecord]` function and mapping its fields to the record's
units; the panel, signals, planner and report work unchanged.
"""
