#!/usr/bin/env python3
"""Stress IPC / vec-env paths that fail in e2e gate (BACKLOG 5.0 diagnostics).

Phases mirror gate failure modes without a full benchmark_train run:

  bridge_parallel — 8 FCEUX, STEP-only (benchmark_bridge n=8 class)
  vec_rollout_1   — SubprocVecEnv, ~one PPO rollout of reset storm (ep_len~2)
  ppo_spike           — CPU/RAM spike like PPO update (parent only)
  ppo_spike_with_vec  — same spike while SubprocVecEnv / FCEUX stay alive (compound B4)
  vec_rollout_2       — second rollout in the same vec session (typical gate crash zone)

Artifacts: stdout only; bridge under tmp/bridge/{train_,bench_} via env_factory.

Usage:
  ./.venv/Scripts/python.exe scripts/stress_e2e_gate.py --quick   # ~8–12 min
  ./.venv/Scripts/python.exe scripts/stress_e2e_gate.py --full    # ~18–25 min
  ./.venv/Scripts/python.exe scripts/run_smoke.py --suite stress
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from fceux_bridge import FceuxBridge  # noqa: E402
from project_paths import artifact_quarantine_dir, mission_dir  # noqa: E402
from train.env_factory import build_vec_env, cleanup_bridge_sessions, preflight_bridge_sessions  # noqa: E402
from train.session_report import SCHEMA_VERSION, host_info, parse_failure_rank, phase_record  # noqa: E402
from train.thread_limits import configure_train_threads  # noqa: E402

# Gate-shaped defaults (benchmark_train: n_steps=128, n_envs=8, 2 rollout's)
GATE_N_ENVS = 8
GATE_N_STEPS = 128
GATE_BATCH_SIZE = 256
GATE_N_EPOCHS = 4

PHASE_NAMES = (
    "bridge_parallel",
    "vec_rollout_1",
    "ppo_spike",
    "ppo_spike_with_vec",
    "vec_rollout_2",
)


@dataclass
class PhaseResult:
    name: str
    ok: bool
    elapsed_s: float
    detail: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class StressReport:
    mode: str
    n_envs: int
    cycles_per_rollout: int
    bridge_steps: int
    phases: list[PhaseResult] = field(default_factory=list)
    wall_s: float = 0.0
    preflight_orphans_before: int = 0

    @property
    def ok(self) -> bool:
        return all(p.ok for p in self.phases)


def _stress_phase_record(result: PhaseResult) -> dict[str, Any]:
    failures = result.detail.get("failures", [])
    auto_dones = result.detail.get("auto_dones")
    rank = failures[0]["rank"] if failures else parse_failure_rank(result.error)
    detail = {
        key: value
        for key, value in result.detail.items()
        if key not in {"auto_dones", "failures"}
    }
    if failures:
        detail["failures"] = failures
    return phase_record(
        phase=result.name,
        ok=result.ok,
        wall_s=result.elapsed_s,
        error=result.error,
        rank=rank,
        auto_dones=auto_dones,
        detail=detail or None,
    )


def build_stress_report_payload(report: StressReport, *, game: str, mission: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "stress_e2e_gate",
        "ok": report.ok,
        "host": host_info(),
        "preflight_orphans_before": report.preflight_orphans_before,
        "game": game,
        "mission": mission,
        "mode": report.mode,
        "n_envs": report.n_envs,
        "cycles_per_rollout": report.cycles_per_rollout,
        "bridge_steps": report.bridge_steps,
        "wall_s": round(report.wall_s, 2),
        "phases": [_stress_phase_record(phase) for phase in report.phases],
    }


def _resolve_save_state(mission: Path, arg: str | None) -> str:
    if arg:
        return arg
    for rel in ("states/cp0.fc0", "states/cp1.fc0"):
        if (mission / rel).is_file():
            return rel
    raise FileNotFoundError(f"No save state in {mission / 'states'}")


def _bridge_parallel_worker(
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


def run_bridge_parallel(
    *,
    mission: Path,
    game_id: str,
    n_envs: int,
    save_state: str,
    frame_skip: int,
    steps_per_env: int,
) -> PhaseResult:
    name = "bridge_parallel"
    print(f"\n=== phase {name} (n={n_envs}, steps/env={steps_per_env}, STEP-only) ===")
    t0 = time.perf_counter()
    ctx = mp.get_context("spawn")
    out_q: mp.Queue = ctx.Queue()
    procs = [
        ctx.Process(
            target=_bridge_parallel_worker,
            args=(out_q, str(mission), game_id, rank, save_state, frame_skip, steps_per_env),
        )
        for rank in range(n_envs)
    ]
    for p in procs:
        p.start()
    errors: list[str] = []
    failures: list[dict[str, Any]] = []
    worker_elapsed: list[float] = []
    for _ in procs:
        rank, elapsed, err = out_q.get()
        if err:
            failures.append({"rank": rank, "error": err})
            errors.append(f"rank {rank}: {err}")
        else:
            worker_elapsed.append(elapsed)
    for p in procs:
        p.join(timeout=max(120, steps_per_env * 2))
        if p.is_alive():
            p.terminate()
            errors.append(f"rank {p.pid}: join timeout")
    wall = time.perf_counter() - t0
    if errors:
        return PhaseResult(
            name=name,
            ok=False,
            elapsed_s=wall,
            error="; ".join(errors),
            detail={"steps_per_env": steps_per_env, "n_envs": n_envs, "failures": failures},
        )
    total_steps = n_envs * steps_per_env
    eps = total_steps / wall if wall > 0 else 0.0
    print(f"  OK wall={wall:.1f}s env_steps/s={eps:.2f} worker_s={worker_elapsed}")
    return PhaseResult(
        name=name,
        ok=True,
        elapsed_s=wall,
        detail={
            "steps_per_env": steps_per_env,
            "n_envs": n_envs,
            "env_steps_per_s": round(eps, 2),
            "worker_elapsed_s": [round(x, 1) for x in worker_elapsed],
        },
    )


def run_vec_rollout(
    *,
    game_id: str,
    mission_id: str,
    n_envs: int,
    save_state: str,
    cycles: int,
    phase_name: str,
    vec,
    rng: np.random.Generator,
) -> tuple[PhaseResult, Any]:
    """Step SubprocVecEnv for `cycles` rounds; reuse vec across rollout_1/2."""
    print(f"\n=== phase {phase_name} (n={n_envs}, cycles={cycles}, SubprocVecEnv) ===")
    t0 = time.perf_counter()
    forced_resets = 0
    auto_dones = 0
    try:
        n_actions = vec.action_space.n
        for cycle in range(1, cycles + 1):
            actions = rng.integers(0, n_actions, size=n_envs)
            _obs, rewards, dones, _infos = vec.step(actions)
            auto_dones += int(np.sum(dones))
            if cycle <= 3 or cycle == cycles:
                print(
                    f"  cycle {cycle}: dones_sum={int(np.sum(dones))} "
                    f"sample_rewards={rewards[:3].tolist()}..."
                )
        elapsed = time.perf_counter() - t0
        print(
            f"  OK elapsed={elapsed:.1f}s auto_dones={auto_dones} "
            f"forced_resets={forced_resets}"
        )
        return (
            PhaseResult(
                name=phase_name,
                ok=True,
                elapsed_s=elapsed,
                detail={
                    "cycles": cycles,
                    "n_envs": n_envs,
                    "auto_dones": auto_dones,
                    "forced_resets": forced_resets,
                },
            ),
            vec,
        )
    except Exception as e:
        elapsed = time.perf_counter() - t0
        return (
            PhaseResult(
                name=phase_name,
                ok=False,
                elapsed_s=elapsed,
                error=repr(e),
                detail={"cycles": cycles, "auto_dones": auto_dones},
            ),
            vec,
        )


def _execute_ppo_spike_compute(*, batch_size: int, n_epochs: int) -> None:
    import torch

    obs = torch.randn(batch_size, 4, 84, 84)
    for epoch in range(n_epochs):
        flat = obs.reshape(batch_size, -1)
        w1 = torch.randn(flat.shape[1], 512, requires_grad=True)
        w2 = torch.randn(512, 64, requires_grad=True)
        h = torch.relu(flat @ w1)
        out = h @ w2
        loss = out.pow(2).mean()
        loss.backward()
        if epoch == 0:
            print(f"  epoch {epoch + 1}/{n_epochs} loss={loss.detach().item():.4f}")
    del obs, w1, w2, h, out, loss


def run_ppo_spike(*, batch_size: int, n_epochs: int, threads: int, n_envs: int) -> PhaseResult:
    """CPU/RAM spike comparable to PPO policy update (parent only)."""
    name = "ppo_spike"
    print(f"\n=== phase {name} (batch={batch_size}, epochs={n_epochs}, threads={threads}) ===")
    t0 = time.perf_counter()
    try:
        configure_train_threads(n_envs=n_envs, threads=threads)
        _execute_ppo_spike_compute(batch_size=batch_size, n_epochs=n_epochs)
        elapsed = time.perf_counter() - t0
        print(f"  OK elapsed={elapsed:.1f}s")
        return PhaseResult(
            name=name,
            ok=True,
            elapsed_s=elapsed,
            detail={"batch_size": batch_size, "n_epochs": n_epochs, "threads": threads},
        )
    except Exception as e:
        elapsed = time.perf_counter() - t0
        return PhaseResult(
            name=name,
            ok=False,
            elapsed_s=elapsed,
            error=repr(e),
        )


def run_ppo_spike_with_vec(
    *,
    vec,
    n_envs: int,
    batch_size: int,
    n_epochs: int,
    threads: int,
    rng: np.random.Generator,
) -> PhaseResult:
    """PPO update spike while SubprocVecEnv workers / FCEUX remain alive (FAIL_REPORT B4)."""
    name = "ppo_spike_with_vec"
    print(
        f"\n=== phase {name} (n={n_envs}, batch={batch_size}, "
        f"epochs={n_epochs}, live SubprocVecEnv) ==="
    )
    t0 = time.perf_counter()
    vec_steps = 0
    try:
        configure_train_threads(n_envs=n_envs, threads=threads)
        n_actions = vec.action_space.n
        pre_actions = rng.integers(0, n_actions, size=n_envs)
        vec.step(pre_actions)
        vec_steps += 1
        _execute_ppo_spike_compute(batch_size=batch_size, n_epochs=n_epochs)
        post_actions = rng.integers(0, n_actions, size=n_envs)
        vec.step(post_actions)
        vec_steps += 1
        elapsed = time.perf_counter() - t0
        print(f"  OK elapsed={elapsed:.1f}s vec_steps={vec_steps} (FCEUX alive)")
        return PhaseResult(
            name=name,
            ok=True,
            elapsed_s=elapsed,
            detail={
                "batch_size": batch_size,
                "n_epochs": n_epochs,
                "threads": threads,
                "n_envs": n_envs,
                "vec_steps": vec_steps,
            },
        )
    except Exception as e:
        elapsed = time.perf_counter() - t0
        return PhaseResult(
            name=name,
            ok=False,
            elapsed_s=elapsed,
            error=repr(e),
            detail={"vec_steps": vec_steps, "n_envs": n_envs},
        )


def run_stress(args: argparse.Namespace) -> StressReport:
    mission = mission_dir(args.game, args.mission)
    save_state = _resolve_save_state(mission, args.save_state)
    phases_filter = set(args.phase) if args.phase else set(PHASE_NAMES)

    if args.quick:
        cycles = args.cycles or GATE_N_STEPS // 2
        bridge_steps = args.bridge_steps or GATE_N_STEPS // 2
        mode = "quick"
    else:
        cycles = args.cycles or GATE_N_STEPS
        bridge_steps = args.bridge_steps or GATE_N_STEPS
        mode = "full"

    report = StressReport(
        mode=mode,
        n_envs=args.n_envs,
        cycles_per_rollout=cycles,
        bridge_steps=bridge_steps,
    )

    print(
        f"stress_e2e_gate: mode={mode} n_envs={args.n_envs} "
        f"cycles/rollout={cycles} bridge_steps={bridge_steps} "
        f"phases={','.join(PHASE_NAMES)}"
    )

    preflight_orphans = preflight_bridge_sessions(label="stress_e2e_gate")
    report.preflight_orphans_before = preflight_orphans

    wall_t0 = time.perf_counter()
    vec = None
    rng = np.random.default_rng(0)

    try:
        if "bridge_parallel" in phases_filter:
            pr = run_bridge_parallel(
                mission=mission,
                game_id=args.game,
                n_envs=args.n_envs,
                save_state=save_state,
                frame_skip=args.frame_skip,
                steps_per_env=bridge_steps,
            )
            report.phases.append(pr)
            if not pr.ok and args.fail_fast:
                return report
            cleanup_bridge_sessions("bench_")

        need_vec = any(
            phase in phases_filter
            for phase in ("vec_rollout_1", "vec_rollout_2", "ppo_spike_with_vec")
        )
        if need_vec:
            vec = build_vec_env(
                game_id=args.game,
                mission_id=args.mission,
                n_envs=args.n_envs,
                save_state=save_state,
                subproc=True,
            )
            obs = vec.reset()
            print(f"vec env ready shape={obs.shape}")

        if "vec_rollout_1" in phases_filter and vec is not None:
            pr, vec = run_vec_rollout(
                game_id=args.game,
                mission_id=args.mission,
                n_envs=args.n_envs,
                save_state=save_state,
                cycles=cycles,
                phase_name="vec_rollout_1",
                vec=vec,
                rng=rng,
            )
            report.phases.append(pr)
            if not pr.ok and args.fail_fast:
                return report

        if "ppo_spike" in phases_filter:
            pr = run_ppo_spike(
                batch_size=args.batch_size,
                n_epochs=args.n_epochs,
                threads=args.threads,
                n_envs=args.n_envs,
            )
            report.phases.append(pr)
            if not pr.ok and args.fail_fast:
                return report

        if "ppo_spike_with_vec" in phases_filter and vec is not None:
            pr = run_ppo_spike_with_vec(
                vec=vec,
                n_envs=args.n_envs,
                batch_size=args.batch_size,
                n_epochs=args.n_epochs,
                threads=args.threads,
                rng=rng,
            )
            report.phases.append(pr)
            if not pr.ok and args.fail_fast:
                return report

        if "vec_rollout_2" in phases_filter and vec is not None:
            pr, vec = run_vec_rollout(
                game_id=args.game,
                mission_id=args.mission,
                n_envs=args.n_envs,
                save_state=save_state,
                cycles=cycles,
                phase_name="vec_rollout_2",
                vec=vec,
                rng=rng,
            )
            report.phases.append(pr)

    finally:
        if vec is not None:
            try:
                vec.close()
            except (EOFError, BrokenPipeError):
                pass
        cleanup_bridge_sessions("train_")
        cleanup_bridge_sessions("bench_")

    report.wall_s = time.perf_counter() - wall_t0
    return report


def _print_summary(report: StressReport) -> None:
    print("\n=== stress_e2e_gate summary ===")
    for p in report.phases:
        status = "OK" if p.ok else "FAIL"
        err = f"  error={p.error}" if p.error else ""
        print(f"  {p.name:18} {status:4}  {p.elapsed_s:7.1f}s{err}")
    print(f"  {'TOTAL':18} {'OK' if report.ok else 'FAIL':4}  {report.wall_s:7.1f}s")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="E2E gate stress (IPC thin spots) without full benchmark_train"
    )
    parser.add_argument("--game", default="rushn_attack")
    parser.add_argument("--mission", default="m1")
    parser.add_argument("--save-state", default=None)
    parser.add_argument("--n-envs", type=int, default=GATE_N_ENVS)
    parser.add_argument("--frame-skip", type=int, default=4)
    parser.add_argument("--cycles", type=int, default=None, help="vec steps per rollout (default: 128 full / 64 quick)")
    parser.add_argument("--bridge-steps", type=int, default=None, help="STEP-only steps per env (default: same as --cycles)")
    parser.add_argument("--batch-size", type=int, default=GATE_BATCH_SIZE)
    parser.add_argument("--n-epochs", type=int, default=GATE_N_EPOCHS)
    parser.add_argument("--threads", type=int, default=2, help="torch threads for ppo_spike")
    parser.add_argument(
        "--phase",
        action="append",
        choices=PHASE_NAMES,
        help="run subset only (repeatable); default: all phases",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--quick", action="store_true", help="half rollout depth (~8–12 min)")
    mode.add_argument("--full", action="store_true", help="gate-shaped depth (~18–25 min)")
    parser.add_argument("--fail-fast", action="store_true", default=True)
    parser.add_argument("--no-fail-fast", action="store_false", dest="fail_fast")
    parser.add_argument("--json-out", default=None, help="default: tmp/smoke/stress_e2e/report.json")
    args = parser.parse_args()

    if not args.quick and not args.full:
        args.quick = True

    report = run_stress(args)
    _print_summary(report)

    out = Path(args.json_out) if args.json_out else (
        artifact_quarantine_dir("smoke", "stress_e2e") / "report.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = build_stress_report_payload(
        report,
        game=args.game,
        mission=args.mission,
    )
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report: {out}")

    if not report.ok:
        failed = [p.name for p in report.phases if not p.ok]
        print(f"STRESS FAIL: {', '.join(failed)}")
        sys.exit(1)
    print("STRESS OK")


if __name__ == "__main__":
    main()
