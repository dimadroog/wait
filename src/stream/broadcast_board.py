"""Агрегаты пула genN и дельта vs genN−1 для broadcast board."""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonl_logs import gen_log_path, load_jsonl, normalize_model_version
from project_paths import repo_root

BOARD_SCHEMA = "broadcast_board/v1"
DEFAULT_SUPPORT_LINE = "Поддержать проект"


def prev_model_version(model_version: str) -> str | None:
    """gen3 → gen2; иначе None."""
    m = re.fullmatch(r"gen(\d+)", normalize_model_version(model_version), flags=re.IGNORECASE)
    if not m:
        return None
    n = int(m.group(1))
    if n <= 0:
        return None
    return f"gen{n - 1}"


def aggregate_attempts(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Минимальные агрегаты eval для board: reach CP_k, стена смертей, frontier."""
    n = len(records)
    if n == 0:
        return {
            "episodes": 0,
            "frontier_cp": -1,
            "mission_clear_rate": 0.0,
            "reach_cp": {},
            "death_wall": None,
        }

    cps = [int(r.get("max_checkpoint", -1)) for r in records]
    frontier = max(cps)
    max_cp_levels = max(frontier, 0)
    reach: dict[str, float] = {}
    for k in range(0, max_cp_levels + 1):
        reach[str(k)] = round(sum(1 for c in cps if c >= k) / n, 4)

    clears = sum(1 for r in records if r.get("mission_clear"))
    death_counts: Counter[tuple[str, int]] = Counter()
    for r in records:
        if not r.get("died"):
            continue
        room = str(r.get("death_room") or "")
        bucket = r.get("death_x_bucket")
        if bucket is None and r.get("death_x") is not None:
            bucket = int(r["death_x"]) // 16
        if bucket is None:
            continue
        death_counts[(room, int(bucket))] += 1

    wall = None
    if death_counts:
        (room, bucket), count = death_counts.most_common(1)[0]
        wall = {
            "death_room": room,
            "death_x_bucket": bucket,
            "count": count,
            "share": round(count / n, 4),
        }

    return {
        "episodes": n,
        "frontier_cp": frontier,
        "mission_clear_rate": round(clears / n, 4),
        "reach_cp": reach,
        "death_wall": wall,
    }


def delta_aggregates(curr: dict[str, Any], prev: dict[str, Any] | None) -> dict[str, Any]:
    """Дельта curr vs prev для board (доля до CP_k, frontier, стена)."""
    if prev is None:
        return {
            "available": False,
            "frontier_cp": {"curr": curr.get("frontier_cp", -1), "prev": None},
            "reach_cp": {},
            "death_wall": {"curr": curr.get("death_wall"), "prev": None},
        }

    reach: dict[str, dict[str, float | None]] = {}
    keys = sorted(
        set(curr.get("reach_cp") or {}) | set(prev.get("reach_cp") or {}),
        key=lambda x: int(x),
    )
    for k in keys:
        c = (curr.get("reach_cp") or {}).get(k)
        p = (prev.get("reach_cp") or {}).get(k)
        reach[k] = {
            "curr": c,
            "prev": p,
            "delta": round(float(c) - float(p), 4) if c is not None and p is not None else None,
        }

    return {
        "available": True,
        "frontier_cp": {
            "curr": curr.get("frontier_cp", -1),
            "prev": prev.get("frontier_cp", -1),
            "delta": int(curr.get("frontier_cp", -1)) - int(prev.get("frontier_cp", -1)),
        },
        "mission_clear_rate": {
            "curr": curr.get("mission_clear_rate", 0.0),
            "prev": prev.get("mission_clear_rate", 0.0),
            "delta": round(
                float(curr.get("mission_clear_rate", 0.0))
                - float(prev.get("mission_clear_rate", 0.0)),
                4,
            ),
        },
        "reach_cp": reach,
        "death_wall": {"curr": curr.get("death_wall"), "prev": prev.get("death_wall")},
    }


def build_broadcast_board(
    *,
    model_version: str,
    curr_records: list[dict[str, Any]],
    prev_records: list[dict[str, Any]] | None = None,
    mode: str = "open",
    support_line: str | None = DEFAULT_SUPPORT_LINE,
    game: str = "rushn_attack",
    mission: str = "m1",
) -> dict[str, Any]:
    """Контракт JSON для OBS Browser Source / streaming/board/."""
    version = normalize_model_version(model_version)
    curr_agg = aggregate_attempts(curr_records)
    prev_ver = prev_model_version(version)
    prev_agg = aggregate_attempts(prev_records) if prev_records is not None else None
    payload: dict[str, Any] = {
        "schema": BOARD_SCHEMA,
        "mode": mode,
        "game": game,
        "mission": mission,
        "model_version": version,
        "prev_model_version": prev_ver,
        "frontier": {
            "max_checkpoint": curr_agg["frontier_cp"],
            "death_wall": curr_agg["death_wall"],
        },
        "eval": curr_agg,
        "delta": delta_aggregates(curr_agg, prev_agg),
        "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if support_line:
        payload["support_line"] = support_line
    return payload


def write_broadcast_board(
    payload: dict[str, Any],
    dest: Path,
) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if dest.exists():
        dest.unlink()
    tmp.rename(dest)
    return dest


def default_board_paths(mission_logs: Path, model_version: str) -> tuple[Path, Path]:
    """logs/genN/broadcast_board.json и копия в streaming/board/ для OBS."""
    version = normalize_model_version(model_version)
    pool = mission_logs / version / "broadcast_board.json"
    obs = repo_root() / "streaming" / "board" / "broadcast_board.json"
    return pool, obs


def load_pool_attempts(logs_dir: Path, model_version: str) -> list[dict[str, Any]]:
    path = gen_log_path(logs_dir, model_version, "attempts", mkdir=False)
    if not path.is_file():
        return []
    return load_jsonl(path)
