#!/usr/bin/env python3
"""RAM-разведка: FM2 в FCEUX → jsonl → candidates; mission resolve — только с --write-ram-map."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from project_paths import add_game_mission_arguments, resolve_cli_reference_fm2  # noqa: E402
from ram_scout import format_scout_summary, run_ram_scout  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "RAM scout via FM2 replay. Scope — по пути FM2 (или workspace clear.fm2). "
            "cwd= у FCEUX — только staging, не выбор плагина."
        )
    )
    parser.add_argument(
        "fm2",
        nargs="?",
        default=None,
        help=(
            "путь к FM2 от корня репо: games/<game>/reference/<file>.fm2 (shell) или "
            "games/<game>/missions/<mission>/reference/<file>.fm2 (mission). "
            "Если опущен — missions/<workspace>/reference/clear.fm2"
        ),
    )
    add_game_mission_arguments(parser)
    parser.add_argument(
        "--round",
        default=None,
        help="id раунда (default: stem имени FM2); для shell — подкаталог scout/<round>/",
    )
    parser.add_argument("--timeout", type=float, default=600.0, help="секунд на проигрывание")
    parser.add_argument(
        "--write-ram-map",
        action="store_true",
        help="mission: записать config/ram_resolve.json + ram_map.md (иначе только сырой scout/candidates)",
    )
    parser.add_argument(
        "--no-ram-map",
        action="store_true",
        help=argparse.SUPPRESS,  # deprecated: default уже без записи resolve
    )
    args = parser.parse_args()
    if args.no_ram_map and args.write_ram_map:
        raise SystemExit("нельзя одновременно --write-ram-map и --no-ram-map")
    if args.no_ram_map:
        print("warning: --no-ram-map deprecated (default: не писать ram_resolve)", file=sys.stderr)

    try:
        fm2, game_id, scope, mission = resolve_cli_reference_fm2(
            args.fm2, game=args.game, mission=args.mission
        )
    except (FileNotFoundError, ValueError) as e:
        raise SystemExit(str(e)) from e

    result = run_ram_scout(
        fm2=fm2,
        game_id=game_id,
        scope=scope,
        mission=mission,
        round_id=args.round,
        timeout=float(args.timeout),
        write_ram_map=bool(args.write_ram_map),
    )
    for line in format_scout_summary(result):
        print(line)


if __name__ == "__main__":
    main()
