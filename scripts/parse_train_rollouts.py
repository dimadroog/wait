#!/usr/bin/env python3
"""Сводка wall_rollout из rollouts.jsonl (RolloutMetricsCallback)."""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from project_paths import repo_root  # noqa: E402


def _load(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.is_file():
        raise SystemExit(f"jsonl not found: {path}")
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def summarize(rows: list[dict]) -> dict:
    walls = [float(r["wall_rollout_s"]) for r in rows if r.get("wall_rollout_s") is not None]
    rates = [float(r["env_steps_per_s"]) for r in rows if r.get("env_steps_per_s") is not None]
    avails = [float(r["avail_phys_mb"]) for r in rows if r.get("avail_phys_mb") is not None]

    def _at(i: int) -> dict | None:
        return rows[i] if 0 <= i < len(rows) else None

    out: dict = {
        "n_rollouts": len(rows),
        "wall_s_mean": round(statistics.mean(walls), 2) if walls else None,
        "wall_s_stdev": round(statistics.stdev(walls), 2) if len(walls) > 1 else None,
        "wall_s_min": round(min(walls), 2) if walls else None,
        "wall_s_max": round(max(walls), 2) if walls else None,
        "rate_mean": round(statistics.mean(rates), 3) if rates else None,
        "rate_last5_mean": (
            round(statistics.mean(rates[-5:]), 3) if len(rates) >= 5 else (round(statistics.mean(rates), 3) if rates else None)
        ),
        "rollout_1": _at(0),
        "rollout_10": _at(9),
        "rollout_20": _at(19),
        "rollout_last": _at(len(rows) - 1) if rows else None,
        "avail_phys_mb_min": round(min(avails), 1) if avails else None,
        "avail_phys_mb_max": round(max(avails), 1) if avails else None,
    }
    if len(walls) >= 10:
        early = statistics.mean(walls[:5])
        late = statistics.mean(walls[-5:])
        out["wall_late_over_early"] = round(late / early, 2) if early > 0 else None
        out["degraded"] = bool(out["wall_late_over_early"] and out["wall_late_over_early"] >= 2.0)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Summarize rollout metrics JSONL")
    p.add_argument("--jsonl", required=True, help="path to rollouts.jsonl")
    p.add_argument("--json", action="store_true", help="print JSON only")
    args = p.parse_args()

    path = Path(args.jsonl)
    if not path.is_absolute():
        path = repo_root() / path

    rows = _load(path)
    summary = summarize(rows)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    print(f"rollouts: {summary['n_rollouts']}  from {path}")
    print(
        f"wall_s: mean={summary['wall_s_mean']} stdev={summary['wall_s_stdev']} "
        f"min={summary['wall_s_min']} max={summary['wall_s_max']}"
    )
    print(f"env_steps/s: mean={summary['rate_mean']} last5={summary['rate_last5_mean']}")
    if summary.get("wall_late_over_early") is not None:
        flag = "DEGRADED" if summary.get("degraded") else "stable"
        print(f"late/early wall: {summary['wall_late_over_early']}x ({flag})")
    if summary.get("avail_phys_mb_min") is not None:
        print(
            f"avail_phys_mb: min={summary['avail_phys_mb_min']} max={summary['avail_phys_mb_max']}"
        )
    for key in ("rollout_1", "rollout_10", "rollout_20", "rollout_last"):
        row = summary.get(key)
        if not row:
            continue
        print(
            f"  {key}: #{row.get('rollout')} wall={row.get('wall_rollout_s')}s "
            f"rate={row.get('env_steps_per_s')} avail_mb={row.get('avail_phys_mb')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
