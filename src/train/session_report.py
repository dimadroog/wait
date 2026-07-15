"""Схема JSON-отчётов stress/benchmark для сравнения сессий (FAIL_REPORT R0.3)."""
from __future__ import annotations

import platform
import re
import time
from typing import Any

SCHEMA_VERSION = 1


def host_info() -> dict[str, str]:
    return {
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "python": platform.python_version(),
        "date": time.strftime("%Y-%m-%d"),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def parse_failure_rank(error: str | None) -> int | None:
    """Извлечь env rank из текста ошибки (train_N, bench_N, SpawnProcess-N)."""
    if not error:
        return None
    for pattern in (
        r"train_(\d+)",
        r"bench_(\d+)",
        r"rank\s+(\d+)",
        r"SpawnProcess-(\d+)",
    ):
        match = re.search(pattern, error)
        if match:
            return int(match.group(1))
    return None


def phase_record(
    *,
    phase: str,
    ok: bool,
    wall_s: float | None,
    error: str | None = None,
    rank: int | None = None,
    auto_dones: int | None = None,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "phase": phase,
        "ok": ok,
        "wall_s": round(wall_s, 2) if wall_s is not None else None,
        "error": error,
        "rank": rank,
        "auto_dones": auto_dones,
    }
    if detail:
        record["detail"] = detail
    return record


def rollout_phase_records(
    *,
    rollout_wall_s: list[float],
    rollout_auto_dones: list[int],
    learn_error: str | None = None,
) -> list[dict[str, Any]]:
    phases: list[dict[str, Any]] = []
    for index, wall in enumerate(rollout_wall_s, start=1):
        dones = rollout_auto_dones[index - 1] if index - 1 < len(rollout_auto_dones) else None
        phases.append(
            phase_record(
                phase=f"rollout_{index}",
                ok=True,
                wall_s=wall,
                auto_dones=dones,
            )
        )
    if learn_error:
        failed_index = len(rollout_wall_s) + 1
        phases.append(
            phase_record(
                phase=f"rollout_{failed_index}",
                ok=False,
                wall_s=None,
                error=learn_error,
                rank=parse_failure_rank(learn_error),
            )
        )
    return phases
