"""Общие утилиты для dated-логов inference (ML_CONCEPT §8)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator


RETENTION_HOURS = 4.0


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_date_prefix(when: datetime | None = None) -> str:
    return (when or utc_now()).strftime("%Y%m%d")


def start_of_utc_day(when: datetime | None = None) -> datetime:
    t = when or utc_now()
    return t.replace(hour=0, minute=0, second=0, microsecond=0)


def retention_cutoff(*, hours: float = RETENTION_HOURS, when: datetime | None = None) -> datetime:
    now = when or utc_now()
    return max(now - timedelta(hours=hours), start_of_utc_day(now))


def dated_log_path(logs_dir: Path, stem: str, when: datetime | None = None) -> Path:
    """logs/YYYYMMDD_{stem}.jsonl"""
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir / f"{utc_date_prefix(when)}_{stem}.jsonl"


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
    hours: float = RETENTION_HOURS,
    when: datetime | None = None,
) -> list[dict[str, Any]]:
    cutoff = retention_cutoff(hours=hours, when=when)
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


def apply_retention(path: Path, *, hours: float = RETENTION_HOURS) -> None:
    """Удалить строки старше retention (но не раньше полуночи UTC)."""
    if not path.is_file():
        return
    kept = load_jsonl_window(path, hours=hours)
    with path.open("w", encoding="utf-8") as f:
        for row in kept:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def append_jsonl(path: Path, record: dict[str, Any], *, retain: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    if retain:
        apply_retention(path)
