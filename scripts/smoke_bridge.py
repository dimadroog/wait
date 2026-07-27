#!/usr/bin/env python3
"""Smoke test: Python ↔ FCEUX bridge IPC."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from fceux_bridge import FceuxBridge  # noqa: E402
from project_paths import (  # noqa: E402
    add_game_mission_arguments,
    apply_resolved_game_mission,
    mission_dir,
    resolve_mission_fm2,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test FCEUX bridge IPC")
    parser.add_argument(
        "fm2",
        nargs="?",
        default=None,
        help="path to FM2 (default: reference/clear.fm2 under workspace mission)",
    )
    add_game_mission_arguments(parser)
    args = parser.parse_args()

    if args.fm2:
        fm2 = args.fm2
    else:
        game, mission_id = apply_resolved_game_mission(args)
        fm2 = str(mission_dir(game, mission_id) / "reference" / "clear.fm2")

    _, game_id, mission = resolve_mission_fm2(fm2)
    state = mission / "save_states" / "cp_gameplay1.fc0"
    if not state.is_file():
        state = mission / "save_states" / "cp_gameplay0.fc0"
    if not state.is_file():
        raise SystemExit(
            f"Missing save state under {mission / 'save_states'}. "
            "Run build_playthrough.py --states-only first."
        )
    rel = state.relative_to(mission).as_posix()

    with FceuxBridge(mission, game_id, frame_skip=4) as bridge:
        bridge.load_state(rel)
        pid = bridge._proc.pid if bridge._proc else None
        bridge.ping()
        print("PING ok (cold start)")

        ram0 = bridge.get_ram()
        print(f"RAM@start: room={ram0['room']} x={ram0['x']} y={ram0['y']}")

        bridge.step("right")
        ram1 = bridge.get_ram()
        print(f"RAM@step:  room={ram1['room']} x={ram1['x']} y={ram1['y']}")

        bridge.load_state(rel)
        if bridge._proc and pid is not None and bridge._proc.pid != pid:
            raise SystemExit("Hot reset failed: FCEUX process was restarted")
        ram_hot = bridge.get_ram()
        print(f"RAM@hot:   room={ram_hot['room']} x={ram_hot['x']} y={ram_hot['y']} (same pid)")

        obs = bridge.get_obs()
        print(f"OBS shape={obs.shape} mean={obs.mean():.1f} min={obs.min()} max={obs.max()}")

        bridge.turbo(True)
        for _ in range(5):
            bridge.step("right")
        ram2 = bridge.get_ram()
        print(f"RAM@turbo: x={ram2['x']}")

    print("OK")


if __name__ == "__main__":
    main()
