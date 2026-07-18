"""Dated JSONL-логи inference: пути, retention window (календарный день UTC+3)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

# Зеркало config/achievements.yaml → retention_tz_offset_hours (календарный день, не airtime).
RETENTION_TZ_OFFSET_HOURS = 3


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def retention_tz(*, offset_hours: float = RETENTION_TZ_OFFSET_HOURS) -> timezone:
    return timezone(timedelta(hours=offset_hours))


def retention_offset_hours_from_config(config: dict[str, Any] | None = None) -> float:
    """Смещение TZ retention из achievements.yaml; иначе дефолт jsonl_logs."""
    if config is None:
        return RETENTION_TZ_OFFSET_HOURS
    if "retention_tz_offset_hours" in config:
        return float(config["retention_tz_offset_hours"])
    return RETENTION_TZ_OFFSET_HOURS


def start_of_retention_day(
    when: datetime | None = None,
    *,
    offset_hours: float = RETENTION_TZ_OFFSET_HOURS,
) -> datetime:
    """Полуночь календарного дня в retention-TZ, как aware UTC datetime."""
    now = when or utc_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local = now.astimezone(retention_tz(offset_hours=offset_hours))
    start_local = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start_local.astimezone(timezone.utc)


def retention_date_prefix(
    when: datetime | None = None,
    *,
    offset_hours: float = RETENTION_TZ_OFFSET_HOURS,
) -> str:
    """YYYYMMDD стены retention-TZ (UTC+3 по умолчанию)."""
    now = when or utc_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local = now.astimezone(retention_tz(offset_hours=offset_hours))
    return local.strftime("%Y%m%d")


# Совместимость со старыми импортами: префикс дня = retention wall date, не UTC midnight.
utc_date_prefix = retention_date_prefix


def retention_cutoff(
    *,
    when: datetime | None = None,
    offset_hours: float = RETENTION_TZ_OFFSET_HOURS,
) -> datetime:
    """Нижняя граница retention window = начало текущего календарного дня (UTC+3)."""
    return start_of_retention_day(when, offset_hours=offset_hours)


def dated_day_dir(
    logs_dir: Path,
    when: datetime | None = None,
    *,
    offset_hours: float = RETENTION_TZ_OFFSET_HOURS,
) -> Path:
    """logs/YYYYMMDD/ — каталог артефактов за день retention (UTC+3)."""
    day = logs_dir / retention_date_prefix(when, offset_hours=offset_hours)
    day.mkdir(parents=True, exist_ok=True)
    return day


def dated_log_path(
    logs_dir: Path,
    stem: str,
    when: datetime | None = None,
    *,
    offset_hours: float = RETENTION_TZ_OFFSET_HOURS,
) -> Path:
    """logs/YYYYMMDD/{stem}.jsonl"""
    return dated_day_dir(logs_dir, when, offset_hours=offset_hours) / f"{stem}.jsonl"


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    if not path.is_file():
        return
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def load_jsonl_window(
    path: Path,
    *,
    when: datetime | None = None,
    offset_hours: float = RETENTION_TZ_OFFSET_HOURS,
) -> list[dict[str, Any]]:
    """Строки с timestamp ≥ полуночи retention-дня; без timestamp — сохранить."""
    cutoff = retention_cutoff(when=when, offset_hours=offset_hours)
    rows: list[dict[str, Any]] = []
    for row in iter_jsonl(path):
        ts = row.get("timestamp")
        if not ts:
            rows.append(row)
            continue
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except ValueError:
            rows.append(row)
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt >= cutoff:
            rows.append(row)
    return rows


def apply_retention(
    path: Path,
    *,
    when: datetime | None = None,
    offset_hours: float = RETENTION_TZ_OFFSET_HOURS,
) -> None:
    """Оставить только строки текущего retention-дня (календарный день UTC+3)."""
    if not path.is_file():
        return
    kept = load_jsonl_window(path, when=when, offset_hours=offset_hours)
    with path.open("w", encoding="utf-8") as f:
        for row in kept:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def append_jsonl(path: Path, record: dict[str, Any], *, retain: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    if retain:
        apply_retention(path)
