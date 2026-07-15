#!/usr/bin/env python3
"""End-to-end PPO train benchmark (BACKLOG 1.9).

Wall-clock env-steps/s на SubprocVecEnv; checkpoint и JSON только в tmp/bench/.
Полный gate-прогон — фаза C; здесь инфраструктура + опциональный замер.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from project_paths import artifact_quarantine_dir, mission_dir, repo_root  # noqa: E402
from train.checkpointing import InterruptHandler, atomic_save_model, checkpoint_zip_path  # noqa: E402
from train.env_factory import build_vec_env, cleanup_bridge_sessions, preflight_bridge_sessions  # noqa: E402
from train.learn_watchdog import (  # noqa: E402
    DEFAULT_LEARN_STALL_TIMEOUT_S,
    DEFAULT_SESSION_WALL_TIMEOUT_S,
    LearnStallError,
    SessionWallTimeoutError,
    learn_with_stall_watchdog,
)
from train.session_report import (  # noqa: E402
    SCHEMA_VERSION,
    host_info,
    parse_failure_rank,
    phase_record,
    rollout_phase_records,
)
from train.thread_limits import configure_train_threads  # noqa: E402
from train.train_ppo import POLICY_KWARGS, _default_save_state  # noqa: E402

HISTORICAL_E2E_ENV_STEPS_PER_S = 0.5  # 4 env, pre-1.x (BACKLOG)
GATE_TIMESTEPS = 2048
FPS_TIMESTEPS = 8192


@dataclass
class TrainBenchmarkMetrics:
    n_envs: int
    n_steps: int
    timesteps_target: int
    timesteps_done: int
    wall_s: float
    env_steps_per_s_wall: float
    rollout_count: int
    warmup_rollouts: int
    env_steps_per_s_steady: float | None
    steady_rollout_wall_s: float | None


class RolloutTimingCallback(BaseCallback):
    """Время rollout'ов и auto_dones для JSON-отчёта (R0.3)."""

    def __init__(self, *, warmup_rollouts: int, verbose: int = 0):
        super().__init__(verbose)
        self.warmup_rollouts = warmup_rollouts
        self.rollout_wall_s: list[float] = []
        self.rollout_auto_dones: list[int] = []
        self._t0: float | None = None
        self._dones_this_rollout = 0

    def _on_rollout_start(self) -> None:
        self._t0 = time.perf_counter()
        self._dones_this_rollout = 0

    def _on_rollout_end(self) -> None:
        if self._t0 is not None:
            self.rollout_wall_s.append(time.perf_counter() - self._t0)
            self.rollout_auto_dones.append(self._dones_this_rollout)
        self._t0 = None

    def _on_step(self) -> bool:
        dones = self.locals.get("dones")
        if dones is not None:
            self._dones_this_rollout += int(np.sum(dones))
        return True


def _resolve_save_state(mission: Path, arg: str | None) -> str:
    if arg:
        return arg
    return _default_save_state(mission)


def _bench_checkpoint_dir(session: str) -> Path:
    """Абсолютный tmp/bench/<session>/ — не mission/checkpoints."""
    return artifact_quarantine_dir("bench", session).resolve()


def _load_bridge_report(path: Path | None) -> dict[str, Any] | None:
    candidates: list[Path] = []
    if path is not None:
        candidates.append(path.resolve())
    candidates.append(repo_root() / "tmp" / "bench" / "bridge_baseline" / "baseline_report.json")
    for candidate in candidates:
        if candidate.is_file():
            return json.loads(candidate.read_text(encoding="utf-8"))
    return None


def _steady_env_steps_per_s(
    rollout_wall_s: list[float],
    *,
    warmup_rollouts: int,
    n_steps: int,
    n_envs: int,
) -> tuple[float | None, float | None]:
    if len(rollout_wall_s) <= warmup_rollouts:
        return None, None
    steady = rollout_wall_s[warmup_rollouts:]
    total_wall = sum(steady)
    if total_wall <= 0:
        return None, None
    steps = n_steps * n_envs * len(steady)
    return steps / total_wall, total_wall


def _print_table(metrics: TrainBenchmarkMetrics, *, bridge_eps: float | None) -> None:
    print()
    print(f"=== PPO e2e train benchmark (n_envs={metrics.n_envs}) ===")
    print(f"  timesteps           {metrics.timesteps_done}/{metrics.timesteps_target}")
    print(f"  wall_s              {metrics.wall_s:8.1f}")
    print(f"  env_steps/s (wall)  {metrics.env_steps_per_s_wall:8.2f}")
    if metrics.env_steps_per_s_steady is not None:
        print(
            f"  env_steps/s (steady) {metrics.env_steps_per_s_steady:8.2f}"
            f"  (rollouts {metrics.warmup_rollouts + 1}..{metrics.rollout_count},"
            f" wall {metrics.steady_rollout_wall_s:.1f}s)"
        )
    else:
        print("  env_steps/s (steady)      n/a  (нужно больше rollout'ов / --warmup-rollouts)")
    if bridge_eps is not None:
        ratio = metrics.env_steps_per_s_wall / bridge_eps if bridge_eps > 0 else 0.0
        print(f"  bridge parallel ref {bridge_eps:8.2f}  (e2e/bridge wall {ratio:.2f}x)")
    hist_ratio = (
        metrics.env_steps_per_s_wall / HISTORICAL_E2E_ENV_STEPS_PER_S
        if HISTORICAL_E2E_ENV_STEPS_PER_S > 0
        else 0.0
    )
    print(
        f"  vs historical ~{HISTORICAL_E2E_ENV_STEPS_PER_S} env-step/s (4 env pre-1.x):"
        f" {hist_ratio:.1f}x wall"
    )
    print()


def run_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    mission = mission_dir(args.game, args.mission)
    save_state = _resolve_save_state(mission, args.save_state)
    bench_dir = _bench_checkpoint_dir(args.session)
    checkpoint_out = (bench_dir / "bench_train.zip").resolve()

    if args.dry_run:
        print(f"bench_dir={bench_dir}")
        print(f"checkpoint_out={checkpoint_out}")
        print(f"json_out={(bench_dir / 'train_report.json').resolve()}")
        return {"dry_run": True, "bench_dir": str(bench_dir)}

    configure_train_threads(n_envs=args.n_envs, threads=args.threads)
    preflight_orphans = preflight_bridge_sessions(label="benchmark_train")

    timing = RolloutTimingCallback(warmup_rollouts=args.warmup_rollouts)
    vec_env = build_vec_env(
        game_id=args.game,
        mission_id=args.mission,
        n_envs=args.n_envs,
        save_state=save_state,
        turbo=True,
        subproc=not args.dummy_vec,
    )

    model = PPO(
        "CnnPolicy",
        vec_env,
        learning_rate=args.learning_rate,
        n_steps=args.n_steps,
        batch_size=args.batch_size,
        n_epochs=args.n_epochs,
        gamma=args.gamma,
        policy_kwargs=POLICY_KWARGS,
        verbose=1 if not args.quiet else 0,
        device="cpu",
    )

    t0 = time.perf_counter()
    learn_error: str | None = None
    interrupted = False
    with InterruptHandler() as interrupt:
        try:
            learn_with_stall_watchdog(
                model,
                vec_env,
                stall_timeout_s=args.learn_stall_timeout,
                wall_timeout_s=args.session_wall_timeout,
                session_start_mono=t0,
                total_timesteps=int(args.timesteps),
                callback=timing,
                progress_bar=False,
                reset_num_timesteps=True,
            )
        except LearnStallError as exc:
            learn_error = repr(exc)
        except SessionWallTimeoutError as exc:
            learn_error = repr(exc)
        except Exception as exc:
            learn_error = repr(exc)
        finally:
            interrupted = interrupt.interrupted
            try:
                vec_env.close()
            except (EOFError, BrokenPipeError):
                pass
            cleanup_bridge_sessions("train_")
            if int(model.num_timesteps) > 0:
                atomic_save_model(model, checkpoint_out)

    if interrupted and learn_error is None:
        learn_error = "interrupted (KeyboardInterrupt/SIGTERM)"

    wall_s = time.perf_counter() - t0
    done = int(model.num_timesteps)
    steady_eps, steady_wall = _steady_env_steps_per_s(
        timing.rollout_wall_s,
        warmup_rollouts=args.warmup_rollouts,
        n_steps=args.n_steps,
        n_envs=args.n_envs,
    )

    metrics = TrainBenchmarkMetrics(
        n_envs=args.n_envs,
        n_steps=args.n_steps,
        timesteps_target=int(args.timesteps),
        timesteps_done=done,
        wall_s=wall_s,
        env_steps_per_s_wall=done / wall_s if wall_s > 0 else 0.0,
        rollout_count=len(timing.rollout_wall_s),
        warmup_rollouts=args.warmup_rollouts,
        env_steps_per_s_steady=steady_eps,
        steady_rollout_wall_s=steady_wall,
    )

    bridge_report = _load_bridge_report(
        Path(args.bridge_report) if args.bridge_report else None
    )
    bridge_eps: float | None = None
    if bridge_report:
        parallel = bridge_report.get("metrics", {}).get("parallel_env_steps_per_s")
        if isinstance(parallel, (int, float)):
            bridge_eps = float(parallel)

    _print_table(metrics, bridge_eps=bridge_eps)

    phases = rollout_phase_records(
        rollout_wall_s=timing.rollout_wall_s,
        rollout_auto_dones=timing.rollout_auto_dones,
        learn_error=learn_error,
    )
    target = int(args.timesteps)
    ok = learn_error is None and done >= target
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "benchmark_train",
        "ok": ok,
        "error": learn_error,
        "failure_rank": parse_failure_rank(learn_error),
        "host": host_info(),
        "preflight_orphans_before": preflight_orphans,
        "game": args.game,
        "mission": args.mission,
        "save_state": save_state,
        "bench_dir": str(bench_dir),
        "checkpoint_out": str(checkpoint_zip_path(checkpoint_out)),
        "mode": args.mode,
        "wall_s": round(wall_s, 2),
        "phases": phases,
        "metrics": asdict(metrics),
        "rollout_wall_s": [round(x, 2) for x in timing.rollout_wall_s],
        "rollout_auto_dones": timing.rollout_auto_dones,
        "comparison": {
            "historical_e2e_env_steps_per_s": HISTORICAL_E2E_ENV_STEPS_PER_S,
            "bridge_parallel_env_steps_per_s": bridge_eps,
            "e2e_over_bridge_wall": (
                metrics.env_steps_per_s_wall / bridge_eps if bridge_eps and bridge_eps > 0 else None
            ),
            "e2e_over_historical_wall": (
                metrics.env_steps_per_s_wall / HISTORICAL_E2E_ENV_STEPS_PER_S
                if HISTORICAL_E2E_ENV_STEPS_PER_S > 0
                else None
            ),
        },
        "notes": {
            "steady_state": "env_steps/s после warmup_rollouts; cold start 8 FCEUX в первом rollout",
            "gate_timesteps": GATE_TIMESTEPS,
            "fps_timesteps": FPS_TIMESTEPS,
            "dummy_vec_invalid_for_19": args.dummy_vec,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="PPO e2e train benchmark (tmp/bench only)")
    parser.add_argument("--game", default="rushn_attack")
    parser.add_argument("--mission", default="m1")
    parser.add_argument("--save-state", default=None)
    parser.add_argument("--session", default="train_e2e", help="tmp/bench/<session>/")
    parser.add_argument("--n-envs", type=int, default=8)
    parser.add_argument("--n-steps", type=int, default=128)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--n-epochs", type=int, default=4)
    parser.add_argument("--gamma", type=float, default=0.99)
    parser.add_argument("--learning-rate", type=float, default=2.5e-4)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument(
        "--mode",
        choices=("gate", "fps", "custom"),
        default="gate",
        help="gate=2048 timesteps (стабильность); fps=8192 (steady fps); custom=--timesteps",
    )
    parser.add_argument("--timesteps", type=int, default=None, help="override --mode timesteps")
    parser.add_argument("--warmup-rollouts", type=int, default=1, help="rollout'ы вне steady fps")
    parser.add_argument("--bridge-report", default=None, help="bridge baseline JSON для сравнения")
    parser.add_argument("--json-out", default=None, help="default: tmp/bench/<session>/train_report.json")
    parser.add_argument("--dummy-vec", action="store_true", help="отладка only; не приёмка 1.9")
    parser.add_argument("--quiet", action="store_true", help="PPO verbose=0")
    parser.add_argument("--dry-run", action="store_true", help="пути tmp/bench, без learn")
    parser.add_argument(
        "--learn-stall-timeout",
        type=float,
        default=DEFAULT_LEARN_STALL_TIMEOUT_S,
        help="abort learn без прогресса timesteps, с (default 300; 0=off)",
    )
    parser.add_argument(
        "--session-wall-timeout",
        type=float,
        default=DEFAULT_SESSION_WALL_TIMEOUT_S,
        help="abort learn по wall-clock сессии, с (default 3600; 0=off)",
    )
    args = parser.parse_args()

    if args.timesteps is not None:
        args.mode = "custom"
    elif args.mode == "gate":
        args.timesteps = GATE_TIMESTEPS
    elif args.mode == "fps":
        args.timesteps = FPS_TIMESTEPS
    else:
        args.timesteps = GATE_TIMESTEPS

    bench_dir = _bench_checkpoint_dir(args.session)
    out_path = Path(args.json_out).resolve() if args.json_out else (bench_dir / "train_report.json").resolve()

    report = run_benchmark(args)
    if args.dry_run:
        print(f"report would be: {out_path}")
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report: {out_path}")
    print(f"checkpoint: {report['checkpoint_out']}")
    if not report.get("ok", True):
        print(f"BENCHMARK FAIL: {report.get('error', 'incomplete timesteps')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
