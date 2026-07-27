#!/usr/bin/env python3
"""Нарезка reference/demos_for_bc/seg_*.npz из manifest + human_playthrough.jsonl."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from playthrough_build import build_demos  # noqa: E402
from project_paths import add_game_mission_arguments, resolve_cli_mission_fm2  # noqa: E402


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Segment playthrough into reference/demos_for_bc/*.npz")
    parser.add_argument(
        "fm2",
        nargs="?",
        default=None,
        help="путь к FM2 от корня репо (для миссии); если опущен — clear.fm2 из workspace",
    )
    add_game_mission_arguments(parser)
    parser.add_argument(
        "--force",
        action="store_true",
        help="перезаписать non-stub demos (иначе отказ, чтобы не портить BC)",
    )
    args = parser.parse_args()
    try:
        _, _, mission = resolve_cli_mission_fm2(args.fm2, game=args.game, mission=args.mission)
    except (FileNotFoundError, ValueError) as e:
        raise SystemExit(str(e)) from e
    paths = build_demos(mission, force=bool(args.force))
    for p in paths:
        print(p)


if __name__ == "__main__":
    main()
