#!/usr/bin/env python3
"""Smoke test: Python ↔ FCEUX bridge IPC."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from fceux_bridge import FceuxBridge  # noqa: E402
from project_paths import resolve_mission_fm2  # noqa: E402


def main() -> None:
    fm2 = "games/rushn_attack/missions/m1/reference/clear.fm2"
    if len(sys.argv) > 1:
        fm2 = sys.argv[1]

    _, game_id, mission = resolve_mission_fm2(fm2)
    state = mission / "states" / "cp1.fc0"
    if not state.is_file():
        raise SystemExit(f"Missing {state}. Run build_playthrough.py first.")

    with FceuxBridge(mission, game_id, frame_skip=4) as bridge:
        bridge.load_state("states/cp1.fc0")
        pid = bridge._proc.pid if bridge._proc else None
        bridge.ping()
        print("PING ok (cold start)")

        ram0 = bridge.get_ram()
        print(f"RAM@start: room={ram0['room']} x={ram0['x']} y={ram0['y']}")

        bridge.step("right")
        ram1 = bridge.get_ram()
        print(f"RAM@step:  room={ram1['room']} x={ram1['x']} y={ram1['y']}")

        bridge.load_state("states/cp1.fc0")
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
