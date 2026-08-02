#!/usr/bin/env python3
"""Сравнение NPZ obs vs live env на human-траектории."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from bc_obs_compare import run_obs_compare  # noqa: E402
from project_paths import add_game_mission_arguments, apply_resolved_game_mission  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="NPZ vs live env obs diff on human trajectory")
    add_game_mission_arguments(parser)
    parser.add_argument("--segment", default="seg_002")
    parser.add_argument("--frame-start", type=int, default=1034)
    parser.add_argument("--frame-end", type=int, default=1300)
    parser.add_argument("--frame-skip", type=int, default=4)
    parser.add_argument("--model", type=Path, default=None, help="optional: pred agree NPZ vs live obs")
    parser.add_argument("--out", type=Path, default=Path("tmp/bench/bc_obs_compare"))
    args = parser.parse_args()

    game_id, mission_id = apply_resolved_game_mission(args)
    report = run_obs_compare(
        game_id,
        mission_id,
        segment_id=args.segment,
        frame_start=args.frame_start,
        frame_end=args.frame_end,
        frame_skip=args.frame_skip,
        model_path=args.model,
        out_dir=args.out.resolve(),
    )
    print(
        f"compared {report.n_compared} steps: mean_mae={report.mean_mae:.6f} "
        f"match_frac={report.mean_match_frac:.4f} first_diverge={report.first_diverge_frame}"
    )
    if report.pred_agree_frac is not None:
        print(f"pred agree NPZ vs live obs: {report.pred_agree_frac:.1%}")
    print(f"wrote {args.out.resolve() / 'obs_compare_report.md'}")


if __name__ == "__main__":
    main()
