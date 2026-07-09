"""Tier-1 smoke: parallel SubprocVecEnv reset/step (8 env, reset storm).

Имитирует конкуренцию bridge_load_lock при коротких эпизодах без полного PPO train.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from train.env_factory import build_vec_env, cleanup_bridge_sessions  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Parallel SubprocVecEnv IPC stress (BACKLOG 1.9)")
    parser.add_argument("--game", default="rushn_attack")
    parser.add_argument("--mission", default="m1")
    parser.add_argument("--n-envs", type=int, default=8)
    parser.add_argument("--save-state", default="states/cp0.fc0")
    parser.add_argument("--cycles", type=int, default=30, help="step rounds on all envs")
    parser.add_argument(
        "--reset-every",
        type=int,
        default=5,
        help="force vec.reset() every N cycles (0 = only initial reset)",
    )
    args = parser.parse_args()

    cleanup_bridge_sessions("train_")
    n = args.n_envs
    rng = np.random.default_rng(0)

    print(f"parallel stress: n_envs={n} cycles={args.cycles} reset_every={args.reset_every}")
    t0 = time.perf_counter()

    vec = build_vec_env(
        game_id=args.game,
        mission_id=args.mission,
        n_envs=n,
        save_state=args.save_state,
        subproc=True,
    )
    resets = 0
    dones_total = 0
    try:
        obs = vec.reset()
        resets += 1
        print(f"initial reset ok shape={obs.shape}")

        n_actions = vec.action_space.n
        for cycle in range(1, args.cycles + 1):
            if args.reset_every > 0 and cycle > 1 and (cycle - 1) % args.reset_every == 0:
                obs = vec.reset()
                resets += 1
                print(f"  cycle {cycle}: forced reset ok")

            actions = rng.integers(0, n_actions, size=n)
            obs, rewards, dones, infos = vec.step(actions)
            dones_total += int(np.sum(dones))

            if cycle <= 3 or cycle == args.cycles:
                print(
                    f"  cycle {cycle}: rewards={rewards.tolist()} "
                    f"dones={dones.tolist()} dones_sum={int(np.sum(dones))}"
                )

        elapsed = time.perf_counter() - t0
        print(
            f"OK n_envs={n} cycles={args.cycles} resets={resets} "
            f"auto_dones={dones_total} elapsed={elapsed:.1f}s"
        )
    finally:
        vec.close()
        cleanup_bridge_sessions("train_")


if __name__ == "__main__":
    main()
