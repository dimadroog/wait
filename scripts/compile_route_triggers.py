#!/usr/bin/env python3
"""Компиляция route_triggers.yaml из routes.yaml (anchor) + scout + manifest."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from project_paths import add_game_mission_arguments, apply_resolved_game_mission, mission_dir  # noqa: E402
from route_trigger_compile import compile_for_mission  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compile config/route_triggers.yaml from anchor CP + ram_scout.jsonl"
    )
    add_game_mission_arguments(parser)
    args = parser.parse_args()
    game_id, mission_id = apply_resolved_game_mission(args)
    mission = mission_dir(game_id, mission_id)
    try:
        out = compile_for_mission(mission, game_id)
    except (FileNotFoundError, ValueError) as e:
        raise SystemExit(str(e)) from e
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
