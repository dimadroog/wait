#!/usr/bin/env python3
"""Проигрывание одного inference FM2 (-playmovie)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from fm2_playback import resolve_mission_relative_path  # noqa: E402
from project_paths import add_game_mission_arguments, apply_resolved_game_mission  # noqa: E402
from stream.play_fm2 import play_input  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Play inference FM2 (-playmovie)")
    parser.add_argument("input", help=".fm2")
    add_game_mission_arguments(parser)
    parser.add_argument("--turbo", action="store_true", help="ускорить replay")
    parser.add_argument(
        "--noicon",
        action="store_true",
        help="скрытое окно (по умолчанию окно видно)",
    )
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--skip-preflight", action="store_true")
    args = parser.parse_args()
    apply_resolved_game_mission(args)

    if not args.skip_preflight:
        from inference_preflight import require_playback_preflight  # noqa: WPS433

        require_playback_preflight(label="play_inference_fm2")

    input_path = resolve_mission_relative_path(Path(args.input), args.game, args.mission)
    if not input_path.is_file():
        raise SystemExit(f"Input not found: {input_path}")

    play_input(
        input_path,
        game=args.game,
        mission=args.mission,
        turbo=bool(args.turbo),
        noicon=bool(args.noicon),
        timeout=float(args.timeout),
    )


if __name__ == "__main__":
    main()
