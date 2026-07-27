#!/usr/bin/env python3
"""Визуальный просмотр self-contained FM2 в окне FCEUX (фаза C1, оператор).

Без turbo / без -noicon: смотреть gameplay с первых кадров.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from fm2_playback import resolve_mission_relative_path  # noqa: E402
from project_paths import add_game_mission_arguments, apply_resolved_game_mission  # noqa: E402
from stream.play_fm2 import play_gui_fm2  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Play self-contained FM2 in FCEUX GUI")
    parser.add_argument("fm2", type=Path, help="path to .fm2")
    add_game_mission_arguments(parser)
    parser.add_argument(
        "--no-refresh-embed",
        action="store_true",
        help="не обновлять embedded savestate (играть как в файле)",
    )
    parser.add_argument(
        "--turbo",
        action="store_true",
        help="ускорить replay (по умолчанию realtime для визуальной проверки)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=0.0,
        help="секунд до kill (0 = до конца movie + 5s)",
    )
    args = parser.parse_args()
    apply_resolved_game_mission(args)

    resolved = resolve_mission_relative_path(args.fm2, args.game, args.mission)
    if not resolved.is_file():
        raise SystemExit(f"FM2 not found: {args.fm2}")

    play_gui_fm2(
        resolved,
        game=args.game,
        mission=args.mission,
        refresh_embed=not bool(args.no_refresh_embed),
        turbo=bool(args.turbo),
        timeout=float(args.timeout),
    )


if __name__ == "__main__":
    main()
