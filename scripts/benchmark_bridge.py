#!/usr/bin/env python3
"""Benchmark FCEUX bridge IPC (BACKLOG 1.5 baseline).

Замеры: cold start, hot reset (LOAD+GET_OBS), step+decode obs.
Без изменений протокола — только stdlib + существующий bridge.
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import platform
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from fceux_bridge import FceuxBridge, bridge_load_lock  # noqa: E402
from project_paths import artifact_quarantine_dir, mission_dir  # noqa: E402


@dataclass
class SingleBridgeMetrics:
    cold_start_ms: float
    hot_reset_ms: float
    hot_reset_load_ms: float
    hot_reset_obs_ms: float
    step_ipc_ms: float
    step_decode_ms: float
    step_total_ms: float
    reset_step_ratio: float


@dataclass
class AggregateMetrics:
    n_envs: int
    step_warmup: int
    step_samples: int
    reset_samples: int
    single: SingleBridgeMetrics
    parallel_env_steps_per_s: float | None = None
    parallel_wall_s: float | None = None


def _bench_single(
    mission: Path,
    game_id: str,
    *,
    session_id: str,
    save_state: str,
    frame_skip: int,
    step_warmup: int,
    step_samples: int,
    reset_samples: int,
) -> SingleBridgeMetrics:
    t0 = time.perf_counter()
    with FceuxBridge(
        mission,
        game_id,
        frame_skip=frame_skip,
        session_id=session_id,
    ) as bridge:
        bridge.start(load_state=save_state)
        bridge.cache_state(Path(save_state).name)
        cold_start_ms = (time.perf_counter() - t0) * 1000.0

        reset_times: list[float] = []
        reset_ipc_times: list[float] = []
        state_name = Path(save_state).name
        for _ in range(reset_samples):
            t_reset = time.perf_counter()
            with bridge_load_lock():
                t_ipc = time.perf_counter()
                obs_data = bridge.load_obs(state_name, timeout=30.0)
                ipc_ms = (time.perf_counter() - t_ipc) * 1000.0
            bridge.decode_obs_from_response(obs_data)
            reset_times.append((time.perf_counter() - t_reset) * 1000.0)
            reset_ipc_times.append(ipc_ms)

        step_ipc_times: list[float] = []
        decode_times: list[float] = []
        total_times: list[float] = []
        for i in range(step_warmup + step_samples):
            t_step = time.perf_counter()
            t_ipc = time.perf_counter()
            bridge_response = bridge.step("right")
            ipc_ms = (time.perf_counter() - t_ipc) * 1000.0
            t_dec = time.perf_counter()
            bridge.decode_obs_from_response(bridge_response)
            dec_ms = (time.perf_counter() - t_dec) * 1000.0
            total_ms = (time.perf_counter() - t_step) * 1000.0
            if i >= step_warmup:
                step_ipc_times.append(ipc_ms)
                decode_times.append(dec_ms)
                total_times.append(total_ms)

    hot_reset_ms = statistics.mean(reset_times)
    step_ipc_ms = statistics.mean(step_ipc_times)
    step_decode_ms = statistics.mean(decode_times)
    step_total_ms = statistics.mean(total_times)
    reset_step_ratio = hot_reset_ms / step_total_ms if step_total_ms > 0 else 0.0

    return SingleBridgeMetrics(
        cold_start_ms=cold_start_ms,
        hot_reset_ms=hot_reset_ms,
        hot_reset_load_ms=statistics.mean(reset_ipc_times),
        hot_reset_obs_ms=0.0,
        step_ipc_ms=step_ipc_ms,
        step_decode_ms=step_decode_ms,
        step_total_ms=step_total_ms,
        reset_step_ratio=reset_step_ratio,
    )


def _parallel_worker(
    out_q: mp.Queue,
    mission_s: str,
    game_id: str,
    rank: int,
    save_state: str,
    frame_skip: int,
    steps: int,
) -> None:
    mission = Path(mission_s)
    session_id = f"bench_{rank}"
    try:
        with FceuxBridge(
            mission,
            game_id,
            frame_skip=frame_skip,
            session_id=session_id,
        ) as bridge:
            bridge.start(load_state=save_state)
            bridge.cache_state(Path(save_state).name)
            t0 = time.perf_counter()
            for _ in range(steps):
                bridge_response = bridge.step("right")
                bridge.decode_obs_from_response(bridge_response)
            elapsed = time.perf_counter() - t0
        out_q.put((rank, elapsed, None))
    except Exception as e:
        out_q.put((rank, 0.0, repr(e)))


def _bench_parallel(
    mission: Path,
    game_id: str,
    *,
    n_envs: int,
    save_state: str,
    frame_skip: int,
    steps_per_env: int,
) -> tuple[float, float]:
    """Wall-clock aggregate env-steps/s with n_envs parallel FCEUX processes."""
    if n_envs <= 1:
        return 0.0, 0.0

    ctx = mp.get_context("spawn")
    out_q: mp.Queue = ctx.Queue()
    procs = [
        ctx.Process(
            target=_parallel_worker,
            args=(out_q, str(mission), game_id, rank, save_state, frame_skip, steps_per_env),
        )
        for rank in range(n_envs)
    ]
    t0 = time.perf_counter()
    for p in procs:
        p.start()
    errors: list[str] = []
    for _ in procs:
        rank, _elapsed, err = out_q.get()
        if err:
            errors.append(f"rank {rank}: {err}")
    for p in procs:
        p.join(timeout=120)
        if p.is_alive():
            p.terminate()
    wall = time.perf_counter() - t0
    if errors:
        raise RuntimeError("; ".join(errors))
    total_steps = n_envs * steps_per_env
    return total_steps / wall, wall


def _resolve_save_state(mission: Path, arg: str | None) -> str:
    if arg:
        return arg
    for rel in ("states/cp1.fc0", "states/cp0.fc0"):
        if (mission / rel).is_file():
            return rel
    raise FileNotFoundError(f"No save state in {mission / 'states'}")


def _print_table(metrics: AggregateMetrics) -> None:
    s = metrics.single
    print()
    print(f"=== FCEUX bridge benchmark (n_envs={metrics.n_envs}) ===")
    print(f"  cold_start_ms       {s.cold_start_ms:8.1f}")
    print(f"  hot_reset_ms        {s.hot_reset_ms:8.1f}  (LOAD_OBS IPC {s.hot_reset_load_ms:.1f})")
    print(f"  step_total_ms       {s.step_total_ms:8.1f}  (IPC {s.step_ipc_ms:.1f} + decode {s.step_decode_ms:.1f})")
    print(f"  env_steps/s (1 proc) {1000.0 / s.step_total_ms:8.2f}")
    print(f"  reset/step ratio    {s.reset_step_ratio:8.2f}  (ep_len~2 -> reset every ~2 steps)")
    if metrics.parallel_env_steps_per_s is not None:
        print(f"  env_steps/s ({metrics.n_envs} parallel) {metrics.parallel_env_steps_per_s:8.2f}  (wall {metrics.parallel_wall_s:.1f}s)")
    ipc_share = 100.0 * s.step_ipc_ms / s.step_total_ms if s.step_total_ms else 0.0
    dec_share = 100.0 * s.step_decode_ms / s.step_total_ms if s.step_total_ms else 0.0
    print(f"  step breakdown      IPC {ipc_share:.0f}% | decode {dec_share:.0f}%")
    print()


def run_benchmark(args: argparse.Namespace) -> dict:
    mission = mission_dir(args.game, args.mission)
    save_state = _resolve_save_state(mission, args.save_state)

    single = _bench_single(
        mission,
        args.game,
        session_id=args.session,
        save_state=save_state,
        frame_skip=args.frame_skip,
        step_warmup=args.step_warmup,
        step_samples=args.step_samples,
        reset_samples=args.reset_samples,
    )

    parallel_eps: float | None = None
    parallel_wall: float | None = None
    if args.n_envs > 1:
        parallel_eps, parallel_wall = _bench_parallel(
            mission,
            args.game,
            n_envs=args.n_envs,
            save_state=save_state,
            frame_skip=args.frame_skip,
            steps_per_env=args.parallel_steps,
        )

    agg = AggregateMetrics(
        n_envs=args.n_envs,
        step_warmup=args.step_warmup,
        step_samples=args.step_samples,
        reset_samples=args.reset_samples,
        single=single,
        parallel_env_steps_per_s=parallel_eps,
        parallel_wall_s=parallel_wall,
    )
    _print_table(agg)

    host = {
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "python": platform.python_version(),
        "date": time.strftime("%Y-%m-%d"),
    }
    return {
        "host": host,
        "game": args.game,
        "mission": args.mission,
        "frame_skip": args.frame_skip,
        "save_state": save_state,
        "metrics": asdict(agg),
        "notes": {
            "bottleneck_hypothesis": "IPC+gdscreenshot+file obs (not torch/PPO)",
            "ep_len_mean_ref": 2,
            "priority_if_reset_dominates": "1.6 before 1.7" if single.reset_step_ratio > 1.0 else "1.7 may help more",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="FCEUX bridge IPC baseline benchmark")
    parser.add_argument("--game", default="rushn_attack")
    parser.add_argument("--mission", default="m1")
    parser.add_argument("--save-state", default=None)
    parser.add_argument("--frame-skip", type=int, default=4)
    parser.add_argument("--n-envs", type=int, default=8, help="parallel FCEUX for aggregate throughput")
    parser.add_argument("--session", default="bench_bridge")
    parser.add_argument("--step-warmup", type=int, default=5)
    parser.add_argument("--step-samples", type=int, default=30)
    parser.add_argument("--reset-samples", type=int, default=10)
    parser.add_argument("--parallel-steps", type=int, default=20, help="steps per env in parallel phase")
    parser.add_argument("--json-out", default=None, help="write report JSON (default: tmp/bench/)")
    args = parser.parse_args()

    out_path: Path | None = None
    if args.json_out:
        out_path = Path(args.json_out)
    else:
        out_dir = artifact_quarantine_dir("bench", "bridge_baseline")
        out_path = out_dir / "baseline_report.json"

    report = run_benchmark(args)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report: {out_path}")


if __name__ == "__main__":
    main()
