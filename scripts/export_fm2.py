#!/usr/bin/env python3
"""Конвертер inference_inputs.jsonl → self-contained .fm2 (фаза C1)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from fm2_export import default_fm2_template, export_fm2  # noqa: E402
from inference_states import resolve_inference_reset_state  # noqa: E402
from jsonl_logs import dated_log_path  # noqa: E402
from project_paths import mission_dir  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export inference_inputs.jsonl to self-contained FM2"
    )
    parser.add_argument("--game", default="rushn_attack")
    parser.add_argument("--mission", default="m1")
    parser.add_argument(
        "--input",
        default=None,
        help="logs/YYYYMMDD/inference_inputs.jsonl (default: сегодня, день retention UTC+3)",
    )
    parser.add_argument("--output", "-o", required=True, help="output .fm2 path")
    parser.add_argument("--episode", type=int, default=None, help="export single episode")
    parser.add_argument("--frame-skip", type=int, default=4)
    parser.add_argument(
        "--template",
        default=None,
        help="FM2 header template (default reference/header.fm2)",
    )
    parser.add_argument(
        "--save-state",
        default=None,
        help="путь к .fc0 для embed (default: save_states/inference_cp0.fc0)",
    )
    args = parser.parse_args()

    mission = mission_dir(args.game, args.mission)
    jsonl = Path(args.input) if args.input else dated_log_path(mission / "logs", "inference_inputs")
    if not jsonl.is_file():
        raise SystemExit(f"Input not found: {jsonl}")

    template = (
        Path(args.template) if args.template else default_fm2_template(args.game, args.mission)
    )
    out = Path(args.output)

    if args.save_state:
        save_state_path = Path(args.save_state)
        if not save_state_path.is_file():
            save_state_path = mission / args.save_state
    else:
        try:
            rel = resolve_inference_reset_state(mission, cp_index=0)
        except FileNotFoundError as exc:
            raise SystemExit(str(exc)) from exc
        save_state_path = mission / rel
    if not save_state_path.is_file():
        raise SystemExit(f"Save state not found for embed: {save_state_path}")

    n = export_fm2(
        jsonl,
        out,
        template=template,
        episode=args.episode,
        frame_skip=args.frame_skip,
        save_state_path=save_state_path,
        game_id=args.game,
        mission_id=args.mission,
    )
    print(f"  embedded savestate: {save_state_path.name}")
    print(f"Wrote {out} ({n} frames)")
    print("Visual test:")
    print(f"  ./.venv/Scripts/python.exe scripts/play_fm2_gui.py {out.as_posix()}")


if __name__ == "__main__":
    main()
