"""Benchmark parallel env step latency (4 FCEUX)."""
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
        save_state="save_states/cp0.fc0",
        subproc=True,
    )
    try:
        vec.reset()
        latencies = []
        for i in range(50):
            t0 = time.perf_counter()
            vec.step([0, 0, 0, 0])
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
