#!/usr/bin/env python3
"""Собрать broadcast_board.json (агрегаты genN + дельта vs genN−1)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from jsonl_logs import resolve_default_model_version  # noqa: E402
from project_paths import mission_dir  # noqa: E402
from stream.broadcast_board import (  # noqa: E402
    DEFAULT_SUPPORT_LINE,
    build_broadcast_board,
    default_board_paths,
    load_pool_attempts,
    prev_model_version,
    write_broadcast_board,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build broadcast_board.json for hybrid episode (OBS board)"
    )
    parser.add_argument("--game", default="rushn_attack")
    parser.add_argument("--mission", default="m1")
    parser.add_argument("--model", default=None, help="models/genN.zip")
    parser.add_argument("--model-version", default=None)
    parser.add_argument(
        "--mode",
        default="open",
        choices=("open", "editorial", "live", "close", "frontier_report"),
        help="режим перебивки на board",
    )
    parser.add_argument(
        "--support-line",
        default=DEFAULT_SUPPORT_LINE,
        help="скромная строка поддержки (пустая строка — не писать)",
    )
    parser.add_argument(
        "--no-support-line",
        action="store_true",
        help="не включать support_line",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="путь JSON (default: logs/<gen>/broadcast_board.json + streaming/board/)",
    )
    args = parser.parse_args()

    mission = mission_dir(args.game, args.mission)
    logs = mission / "logs"
    version = resolve_default_model_version(
        mission, model=args.model, model_version=args.model_version
    )
    curr = load_pool_attempts(logs, version)
    if not curr:
        raise SystemExit(f"No attempts for {version} under {logs}")

    prev_ver = prev_model_version(version)
    prev = load_pool_attempts(logs, prev_ver) if prev_ver else None
    support = None if args.no_support_line else (args.support_line or None)

    payload = build_broadcast_board(
        model_version=version,
        curr_records=curr,
        prev_records=prev,
        mode=args.mode,
        support_line=support,
        game=args.game,
        mission=args.mission,
    )

    pool_path, obs_path = default_board_paths(logs, version)
    dest = Path(args.output) if args.output else pool_path
    write_broadcast_board(payload, dest)
    print(f"Board: {dest}")
    if args.output is None:
        write_broadcast_board(payload, obs_path)
        print(f"OBS copy: {obs_path}")
    d = payload.get("delta") or {}
    fr = (d.get("frontier_cp") or {})
    print(
        f"mode={payload['mode']} gen={version} frontier={payload['frontier']['max_checkpoint']} "
        f"delta_frontier={fr.get('delta')} episodes={payload['eval']['episodes']}"
    )


if __name__ == "__main__":
    main()
