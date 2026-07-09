#!/usr/bin/env python3
"""Пересборка demos/seg_*.npz с реальными obs через FCEUX env (BC)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from demo_record import record_demos  # noqa: E402
from project_paths import resolve_mission_fm2  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Record demos/seg_*.npz with real obs from human_playthrough.jsonl via env"
    )
    parser.add_argument(
        "fm2",
        help="путь к FM2 (для определения миссии): games/.../reference/<file>.fm2",
    )
    parser.add_argument(
        "--segment",
        action="append",
        dest="segments",
        metavar="ID",
        help="только указанные сегменты (seg_001); можно повторить",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="лимит env steps на сегмент (отладка)",
    )
    parser.add_argument("--session", default="record_demos", help="FCEUX bridge session id")
    parser.add_argument(
        "--jobs",
        type=int,
        default=None,
        help="parallel FCEUX workers (default: min(segments, cpu, 8); 1 = sequential)",
    )
    parser.add_argument("--no-turbo", action="store_true", help="FCEUX без turbo")
    args = parser.parse_args()

    try:
        _fm2, game_id, mission = resolve_mission_fm2(args.fm2)
    except (FileNotFoundError, ValueError) as e:
        raise SystemExit(str(e)) from e

    mission_id = mission.name
    paths = record_demos(
        mission,
        game_id,
        mission_id,
        segment_ids=args.segments,
        session_id=args.session,
        turbo=not args.no_turbo,
        max_steps=args.max_steps,
        workers=args.jobs,
    )
    if not paths:
        raise SystemExit("No demos written.")
    print(f"Done: {len(paths)} file(s) in {mission / 'demos'}")


if __name__ == "__main__":
    main()
