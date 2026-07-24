#!/usr/bin/env python3
"""Подготовка hybrid-эпизода: editorial playlist + broadcast board + команды оператора."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from achievements.airtime import measure_playlist_airtime, parse_airtime_hours  # noqa: E402
from achievements.playlist import (  # noqa: E402
    DEFAULT_EDITORIAL_MAX_AIRTIME,
    build_playlist,
)
from jsonl_logs import gen_log_path, resolve_default_model_version  # noqa: E402
from project_paths import mission_dir, repo_root  # noqa: E402
from stream.broadcast_board import (  # noqa: E402
    build_broadcast_board,
    default_board_paths,
    load_pool_attempts,
    prev_model_version,
    write_broadcast_board,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prep hybrid episode: editorial playlist + board JSON + operator steps"
    )
    parser.add_argument("--game", default="rushn_attack")
    parser.add_argument("--mission", default="m1")
    parser.add_argument("--model", default=None)
    parser.add_argument("--model-version", default=None)
    parser.add_argument(
        "--max-airtime",
        default=None,
        help=f"лимит editorial airtime (default из YAML / {DEFAULT_EDITORIAL_MAX_AIRTIME})",
    )
    parser.add_argument("--max-clips", type=int, default=None)
    parser.add_argument(
        "--mode",
        default="open",
        choices=("open", "editorial", "live", "close", "frontier_report"),
    )
    parser.add_argument("--no-support-line", action="store_true")
    parser.add_argument("--no-dedupe", action="store_true")
    args = parser.parse_args()

    mission = mission_dir(args.game, args.mission)
    logs = mission / "logs"
    version = resolve_default_model_version(
        mission, model=args.model, model_version=args.model_version
    )
    attempts = gen_log_path(logs, version, "attempts", mkdir=False)
    if not attempts.is_file():
        raise SystemExit(f"Attempts not found: {attempts}")

    inputs_cand = gen_log_path(logs, version, "inference_inputs", mkdir=False)
    inputs = inputs_cand if inputs_cand.is_file() else None

    max_air_s = None
    if args.max_airtime is not None:
        max_air_s = parse_airtime_hours(args.max_airtime) * 3600.0

    created, manifest_path, clip_count = build_playlist(
        attempts,
        logs,
        inference_inputs_path=inputs,
        game=args.game,
        mission=args.mission,
        dedupe=not args.no_dedupe,
        model_version=version,
        editorial=True,
        max_airtime_seconds=max_air_s,
        max_clips=args.max_clips,
    )

    curr = load_pool_attempts(logs, version)
    prev_ver = prev_model_version(version)
    prev = load_pool_attempts(logs, prev_ver) if prev_ver else None
    payload = build_broadcast_board(
        model_version=version,
        curr_records=curr,
        prev_records=prev,
        mode=args.mode,
        support_line=None if args.no_support_line else "Поддержать проект",
        game=args.game,
        mission=args.mission,
    )
    pool_board, obs_board = default_board_paths(logs, version)
    write_broadcast_board(payload, pool_board)
    write_broadcast_board(payload, obs_board)

    root = repo_root()
    py = ".venv/Scripts/python.exe"
    rel_manifest = (
        manifest_path.resolve().relative_to(root).as_posix() if manifest_path else "(none)"
    )
    model_arg = args.model or f"{version}.zip"

    print("=== hybrid episode prep ===")
    print(f"gen={version} clips={clip_count} slugs={list(created)}")
    if manifest_path:
        air = measure_playlist_airtime(manifest_path)
        print(f"editorial: {manifest_path} airtime={air.seconds:.1f}s ({air.hours:.4f}h)")
    print(f"board: {pool_board}")
    print(f"OBS board: {obs_board}  (file://{obs_board.parent / 'index.html'})")
    print()
    print("Operator flow (local, without Twitch):")
    print("  1. Board (open)     — OBS Browser Source → streaming/board/index.html")
    print(f"  2. Editorial replay — {py} scripts/play_inference_fm2.py {rel_manifest}")
    print(f"  3. Board (live)    — {py} scripts/build_broadcast_board.py --model {model_arg} --mode live")
    print(
        f"  4. Live inference  — {py} src/stream/run_inference.py "
        f"--model {model_arg} --show-window --episodes 3 --stochastic"
    )
    print(f"  5. Board (close)   — {py} scripts/build_broadcast_board.py --model {model_arg} --mode close")


if __name__ == "__main__":
    main()
