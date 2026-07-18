#!/usr/bin/env python3
"""Preflight перед inference / playback: staging/bridge; logs дня keep-by-default."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from inference_preflight import require_inference_preflight, require_playback_preflight  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preflight before inference or playback (day logs kept by default)"
    )
    parser.add_argument("--game", default="rushn_attack")
    parser.add_argument("--mission", default="m1")
    parser.add_argument(
        "--playback-only",
        action="store_true",
        help="только staging/bridge (для play_inference_fm2, без wipe logs/)",
    )
    parser.add_argument(
        "--wipe-day-logs",
        action="store_true",
        help="удалить logs/YYYYMMDD/ текущего retention-дня перед сбором",
    )
    parser.add_argument(
        "--keep-logs",
        action="store_true",
        help=argparse.SUPPRESS,  # deprecated no-op: keep — дефолт
    )
    args = parser.parse_args()

    if args.playback_only:
        require_playback_preflight()
    else:
        require_inference_preflight(
            game=args.game,
            mission=args.mission,
            clean_logs=bool(args.wipe_day_logs),
        )


if __name__ == "__main__":
    main()
