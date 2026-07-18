"""Retention window = календарный день UTC+3 (не sliding hours)."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jsonl_logs import (  # noqa: E402
    RETENTION_TZ_OFFSET_HOURS,
    load_jsonl_window,
    retention_cutoff,
    retention_date_prefix,
    retention_offset_hours_from_config,
    start_of_retention_day,
)


def test_retention_tz_offset_default_matches_yaml_contract() -> None:
    assert RETENTION_TZ_OFFSET_HOURS == 3
    assert retention_offset_hours_from_config({}) == 3
    assert retention_offset_hours_from_config({"retention_tz_offset_hours": 3}) == 3
    assert retention_offset_hours_from_config({"retention_tz_offset_hours": 5}) == 5


def test_start_of_retention_day_is_utc_plus_3_midnight() -> None:
    # 2026-07-18 01:30 UTC = 04:30 UTC+3 → день 2026-07-18, полуночь local = 2026-07-17 21:00 UTC
    when = datetime(2026, 7, 18, 1, 30, tzinfo=timezone.utc)
    start = start_of_retention_day(when)
    assert start == datetime(2026, 7, 17, 21, 0, tzinfo=timezone.utc)
    assert retention_date_prefix(when) == "20260718"


def test_retention_day_rolls_at_utc_plus_3_midnight_not_utc() -> None:
    # 2026-07-17 22:30 UTC = 2026-07-18 01:30 UTC+3 → уже новый день
    after = datetime(2026, 7, 17, 22, 30, tzinfo=timezone.utc)
    assert retention_date_prefix(after) == "20260718"
    assert retention_cutoff(when=after) == datetime(2026, 7, 17, 21, 0, tzinfo=timezone.utc)

    # 2026-07-17 20:59 UTC = 2026-07-17 23:59 UTC+3 → ещё предыдущий день
    before = datetime(2026, 7, 17, 20, 59, tzinfo=timezone.utc)
    assert retention_date_prefix(before) == "20260717"
    assert retention_cutoff(when=before) == datetime(2026, 7, 16, 21, 0, tzinfo=timezone.utc)


def test_load_jsonl_window_keeps_full_calendar_day_not_last_4h(tmp_path: Path) -> None:
    """Попытка утром того же UTC+3 дня остаётся, даже если прошло >4 ч."""
    when = datetime(2026, 7, 18, 15, 0, tzinfo=timezone.utc)  # 18:00 UTC+3
    day_start = retention_cutoff(when=when)
    morning = day_start + timedelta(hours=1)  # 01:00 UTC+3
    prev_evening = day_start - timedelta(minutes=1)

    path = tmp_path / "attempts.jsonl"
    rows = [
        {"episode_id": "old", "timestamp": prev_evening.isoformat().replace("+00:00", "Z")},
        {"episode_id": "morning", "timestamp": morning.isoformat().replace("+00:00", "Z")},
        {"episode_id": "now", "timestamp": when.isoformat().replace("+00:00", "Z")},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    kept = load_jsonl_window(path, when=when)
    ids = [r["episode_id"] for r in kept]
    assert ids == ["morning", "now"]
