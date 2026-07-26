#!/usr/bin/env python3
"""FM2-плейлист по номинациям achievements."""
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
from project_paths import mission_dir  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build inference playlist by achievement nominations")
    parser.add_argument("--game", default="rushn_attack")
    parser.add_argument("--mission", default="m1")
    parser.add_argument("--model", default=None, help="models/genN.zip (для stem пула)")
    parser.add_argument("--model-version", default=None, help="имя пула logs/<version>/")
    parser.add_argument("--attempts", default=None)
    parser.add_argument(
        "--inputs",
        default=None,
        help="inference_inputs.jsonl (fallback export, если нет epNNNN.fm2)",
    )
    parser.add_argument("--no-dedupe", action="store_true", help="не пропускать дубликаты эпизодов в плейлисте")
    parser.add_argument(
        "--editorial",
        action="store_true",
        help="короткий editorial (editorial_order + лимиты)",
    )
    parser.add_argument(
        "--max-airtime",
        default=None,
        help=f"потолок airtime пакета (12m, 8m, …); с --editorial дефолт {DEFAULT_EDITORIAL_MAX_AIRTIME}",
    )
    parser.add_argument("--max-clips", type=int, default=None, help="потолок числа клипов")
    parser.add_argument(
        "--max-per-slug",
        type=int,
        default=None,
        help="макс. клипов на номинацию (editorial default 1)",
    )
    args = parser.parse_args()

    mission = mission_dir(args.game, args.mission)
    logs = mission / "logs"
    if args.attempts:
        attempts = Path(args.attempts)
        version = args.model_version or attempts.parent.name
    else:
        version = resolve_default_model_version(
            mission, model=args.model, model_version=args.model_version
        )
        attempts = gen_log_path(logs, version, "attempts")

    inputs_candidate = (
        Path(args.inputs) if args.inputs else gen_log_path(logs, version, "inference_inputs")
    )
    inputs = inputs_candidate if inputs_candidate.is_file() else None

    if not attempts.is_file():
        raise SystemExit(f"Attempts log not found: {attempts}")

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
        editorial=args.editorial,
        max_airtime_seconds=max_air_s,
        max_clips=args.max_clips,
        max_per_slug=args.max_per_slug,
    )
    if manifest_path:
        print(f"Manifest: {manifest_path} ({clip_count} clips)")
        print(f"Launcher: {manifest_path.with_suffix('.play.cmd')}")
        air = measure_playlist_airtime(manifest_path)
        kind = "editorial" if args.editorial else "playlist"
        print(f"Airtime ({kind}): {air.seconds:.1f}s ({air.hours:.4f}h)")
    else:
        print("No clips matched nominations")
    print(f"Blocks: {len(created)} slug(s), {sum(len(v) for v in created.values())} clips under {logs}")


if __name__ == "__main__":
    main()
