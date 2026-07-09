#!/usr/bin/env python3
"""Конвертер inference_inputs.jsonl → .fm2 (без reference/)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from fm2_export import default_fm2_template, export_fm2  # noqa: E402
from log_utils import dated_log_path  # noqa: E402
from project_paths import mission_dir  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Export inference_inputs.jsonl to FM2")
    parser.add_argument("--game", default="rushn_attack")
    parser.add_argument("--mission", default="m1")
    parser.add_argument(
        "--input",
        default=None,
        help="logs/YYYYMMDD_inference_inputs.jsonl",
    )
    parser.add_argument("--output", "-o", required=True, help="output .fm2 path")
    parser.add_argument("--episode", type=int, default=None, help="export single episode")
    parser.add_argument("--frame-skip", type=int, default=4)
    parser.add_argument("--template", default=None, help="FM2 header template (not reference/)")
    args = parser.parse_args()

    mission = mission_dir(args.game, args.mission)
    jsonl = Path(args.input) if args.input else dated_log_path(mission / "logs", "inference_inputs")
    if not jsonl.is_file():
        raise SystemExit(f"Input not found: {jsonl}")

    template = Path(args.template) if args.template else default_fm2_template(args.game)
    out = Path(args.output)
    n = export_fm2(
        jsonl,
        out,
        template=template,
        episode=args.episode,
        frame_skip=args.frame_skip,
    )
    print(f"Wrote {out} ({n} frames)")


if __name__ == "__main__":
    main()
