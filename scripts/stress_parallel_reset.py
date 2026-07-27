"""Stress auto-reset (LOAD) with parallel envs."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from project_paths import add_game_mission_arguments, apply_resolved_game_mission  # noqa: E402
from train.env_factory import build_vec_env, cleanup_bridge_sessions  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Stress auto-reset with parallel envs")
    add_game_mission_arguments(parser)
    parser.add_argument("--n-envs", type=int, default=4)
    parser.add_argument("--save-state", default="save_states/cp_gameplay0.fc0")
    parser.add_argument("--seconds", type=float, default=90.0)
    args = parser.parse_args()
    apply_resolved_game_mission(args)

    cleanup_bridge_sessions("train_")
    vec = build_vec_env(
        game_id=args.game,
        mission_id=args.mission,
        n_envs=args.n_envs,
        save_state=args.save_state,
        subproc=True,
    )
    try:
        vec.reset()
        resets = 0
        steps = 0
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < args.seconds:
            actions = [vec.action_space.sample() for _ in range(vec.num_envs)]
            _, _, dones, _ = vec.step(actions)
            steps += 1
            resets += int(sum(dones))
            if steps % 20 == 0:
                print(f"steps={steps} auto_resets={resets} last_dones={dones}")
        print(f"OK steps={steps} auto_resets={resets}")
    finally:
        vec.close()
        cleanup_bridge_sessions("train_")


if __name__ == "__main__":
    main()
