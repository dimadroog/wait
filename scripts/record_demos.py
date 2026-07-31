#!/usr/bin/env python3
"""FM2-synced запись reference/demos_for_bc/seg_*.npz для BC."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from demo_record import record_demos  # noqa: E402
from project_paths import add_game_mission_arguments, resolve_cli_mission_fm2  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Запись reference/demos_for_bc/seg_*.npz с FM2-synced obs "
            "(-playmovie clear.fm2, один проход)"
        )
    )
    parser.add_argument(
        "fm2",
        nargs="?",
        default=None,
        help="путь к FM2 от корня репо; default — clear.fm2 миссии",
    )
    add_game_mission_arguments(parser)
    parser.add_argument(
        "--segment",
        action="append",
        dest="segments",
        metavar="ID",
        help="только seg_001 и т.д. (можно повторить)",
    )
    parser.add_argument(
        "--no-strict-quality",
        action="store_true",
        help="не прерывать запись при провале quality gate",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=600.0,
        help="таймаут FCEUX playmovie (сек, default 600)",
    )
    args = parser.parse_args()

    try:
        fm2, game_id, mission = resolve_cli_mission_fm2(
            args.fm2, game=args.game, mission=args.mission
        )
    except (FileNotFoundError, ValueError) as e:
        raise SystemExit(str(e)) from e

    paths = record_demos(
        mission,
        game_id,
        mission.name,
        fm2,
        segment_ids=args.segments,
        timeout_sec=float(args.timeout),
        strict_quality=not args.no_strict_quality,
    )
    if not paths:
        raise SystemExit("No demos written.")
    print(f"Done: {len(paths)} file(s) in {mission / 'reference' / 'demos_for_bc'}")


if __name__ == "__main__":
    main()
