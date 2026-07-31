"""Запись reference/demos_for_bc/seg_*.npz (FM2-synced obs для BC)."""
from __future__ import annotations

from pathlib import Path

from bc_demo_record import RecordResult, record_demos_fm2


def record_demos(
    mission: Path,
    game_id: str,
    mission_id: str,
    fm2: Path,
    *,
    segment_ids: list[str] | None = None,
    timeout_sec: float | None = None,
    strict_quality: bool = True,
) -> list[Path]:
    """Пересобирает reference/demos_for_bc/seg_*.npz через -playmovie clear.fm2."""
    results = record_demos_fm2(
        mission,
        game_id,
        mission_id,
        fm2,
        segment_ids=segment_ids,
        timeout_sec=timeout_sec or 600.0,
        strict_quality=strict_quality,
    )
    return [r.path for r in results]


__all__ = ["RecordResult", "record_demos", "record_demos_fm2"]
