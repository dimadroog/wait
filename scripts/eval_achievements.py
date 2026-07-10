#!/usr/bin/env python3
"""Правила achievements.yaml → tags[] в logs/YYYYMMDD_attempts.jsonl."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from achievements.evaluator import (  # noqa: E402
    evaluate_attempts_file,
    load_achievements_config,
    write_tagged_attempts,
)
from jsonl_logs import dated_log_path  # noqa: E402
from project_paths import mission_dir  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate achievements for attempts log")
    parser.add_argument("--game", default="rushn_attack")
    parser.add_argument("--mission", default="m1")
    parser.add_argument(
        "--attempts",
        default=None,
        help="путь к attempts.jsonl (default: logs/YYYYMMDD_attempts.jsonl)",
    )
    parser.add_argument("--config", default=None, help="config/achievements.yaml")
    args = parser.parse_args()

    mission = mission_dir(args.game, args.mission)
    attempts = Path(args.attempts) if args.attempts else dated_log_path(mission / "logs", "attempts")
    if not attempts.is_file():
        raise SystemExit(f"Attempts log not found: {attempts}")

    cfg_path = Path(args.config) if args.config else None
    config = load_achievements_config(cfg_path) if cfg_path else load_achievements_config()
    records = evaluate_attempts_file(attempts, config=config)
    write_tagged_attempts(attempts, records)

    tagged = sum(1 for r in records if r.get("tags"))
    print(f"Updated {attempts} ({len(records)} rows, {tagged} with tags)")


if __name__ == "__main__":
    main()
