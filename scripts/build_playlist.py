#!/usr/bin/env python3

"""FM2-плейлист по номинациям achievements."""

from __future__ import annotations



import argparse

import sys

from pathlib import Path



_REPO = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(_REPO / "src"))



from achievements.playlist import build_playlist  # noqa: E402

from jsonl_logs import dated_log_path  # noqa: E402

from project_paths import mission_dir  # noqa: E402





def main() -> None:

    parser = argparse.ArgumentParser(description="Build inference playlist by achievement nominations")

    parser.add_argument("--game", default="rushn_attack")

    parser.add_argument("--mission", default="m1")

    parser.add_argument("--attempts", default=None)

    parser.add_argument("--inputs", default=None, help="inference_inputs.jsonl (обязателен)")
    parser.add_argument("--no-dedupe", action="store_true", help="не пропускать дубликаты эпизодов в плейлисте")

    args = parser.parse_args()



    mission = mission_dir(args.game, args.mission)

    logs = mission / "logs"

    attempts = Path(args.attempts) if args.attempts else dated_log_path(logs, "attempts")

    inputs = Path(args.inputs) if args.inputs else dated_log_path(logs, "inference_inputs")

    if not attempts.is_file():
        raise SystemExit(f"Attempts log not found: {attempts}")
    if not inputs.is_file():
        raise SystemExit(f"inference_inputs not found: {inputs}")

    created, manifest_path, clip_count = build_playlist(
        attempts,
        logs,
        inference_inputs_path=inputs,
        game=args.game,
        mission=args.mission,
        dedupe=not args.no_dedupe,
    )
    if manifest_path:
        print(f"Manifest: {manifest_path} ({clip_count} clips)")
        print(f"Launcher: {manifest_path.with_suffix('.play.cmd')}")
    else:
        print("No clips matched nominations")
    print(f"Blocks: {len(created)} slug(s), {sum(len(v) for v in created.values())} clips under {logs}")





if __name__ == "__main__":

    main()

