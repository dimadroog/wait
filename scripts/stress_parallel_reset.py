"""Stress auto-reset (LOAD) with 4 parallel envs."""
from __future__ import annotations

import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from train.env_factory import build_vec_env, cleanup_bridge_sessions  # noqa: E402


def main() -> None:
    cleanup_bridge_sessions("train_")
    vec = build_vec_env(
        game_id="rushn_attack",
        mission_id="m1",
        n_envs=4,
        save_state="states/cp0.fc0",
        subproc=True,
    )
    try:
        vec.reset()
        resets = 0
        steps = 0
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < 90:
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
