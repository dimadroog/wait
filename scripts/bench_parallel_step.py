"""Benchmark parallel env step latency (4 FCEUX)."""
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
    parser = argparse.ArgumentParser(description="Benchmark parallel env step latency")
    add_game_mission_arguments(parser)
    parser.add_argument("--n-envs", type=int, default=4)
    parser.add_argument("--save-state", default="save_states/cp_gameplay0.fc0")
    parser.add_argument("--steps", type=int, default=50)
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
        latencies = []
        n = args.n_envs
        actions = [0] * n
        for i in range(args.steps):
            t0 = time.perf_counter()
            vec.step(actions)
            latencies.append(time.perf_counter() - t0)
            if (i + 1) % 10 == 0:
                print(f"step {i+1}: last={latencies[-1]:.3f}s max={max(latencies):.3f}s")
        print(
            f"done: mean={sum(latencies)/len(latencies):.3f}s "
            f"p95={sorted(latencies)[int(0.95*len(latencies))]:.3f}s "
            f"max={max(latencies):.3f}s"
        )
    finally:
        vec.close()
        cleanup_bridge_sessions("train_")


if __name__ == "__main__":
    main()
