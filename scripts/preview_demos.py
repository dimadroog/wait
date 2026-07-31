#!/usr/bin/env python3
"""PNG-превью reference/demos_for_bc/seg_*.npz → tmp/demos_for_bc/ (визуальная проверка BC)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from demo_preview import (  # noqa: E402
    default_preview_out_dir,
    export_all_demos,
    format_preview_summary,
    quality_check_failures,
)
from obs_contract import OBS_WIDTH
from project_paths import (  # noqa: E402
    add_game_mission_arguments,
    apply_resolved_game_mission,
    mission_dir,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Экспорт PNG-превью из reference/demos_for_bc/seg_*.npz "
            "(сетка + выборочные кадры) в tmp/demos_for_bc/"
        )
    )
    add_game_mission_arguments(parser)
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="каталог вывода (default: tmp/demos_for_bc/)",
    )
    parser.add_argument(
        "--segment",
        action="append",
        dest="segments",
        metavar="ID",
        help="только seg_001 и т.д. (можно повторить); default — все seg_*.npz",
    )
    parser.add_argument(
        "--step-interval",
        type=int,
        default=25,
        help="шаг env между sample PNG (default: 25)",
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=200,
        help="макс. шагов для sample PNG на сегмент (default: 200)",
    )
    parser.add_argument(
        "--grid-cols",
        type=int,
        default=5,
        help="сторона сетки grid.png (5 → 5×5 кадров, default: 5)",
    )
    parser.add_argument(
        "--tile-px",
        type=int,
        default=OBS_WIDTH,
        help=f"размер плитки в grid.png (default: {OBS_WIDTH})",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 если quality gate не пройден (приёмка BC)",
    )
    args = parser.parse_args()

    game_id, mission_id = apply_resolved_game_mission(args)
    mission = mission_dir(game_id, mission_id)
    out = args.out if args.out is not None else default_preview_out_dir()

    try:
        root, results = export_all_demos(
            mission,
            game_id,
            out_dir=out,
            segment_ids=args.segments,
            step_interval=int(args.step_interval),
            max_samples=int(args.max_samples),
            grid_cols=int(args.grid_cols),
            tile_px=int(args.tile_px),
        )
    except (FileNotFoundError, ValueError) as e:
        raise SystemExit(str(e)) from e

    for line in format_preview_summary(root, results):
        print(line)

    if args.check:
        failures = quality_check_failures(results)
        if failures:
            raise SystemExit("Quality gate failed:\n  " + "\n  ".join(failures))


if __name__ == "__main__":
    main()
