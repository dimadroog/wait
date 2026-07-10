"""PPO training на CPU."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import torch
import yaml
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import CallbackList, CheckpointCallback

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "src"))

from project_paths import artifact_quarantine_dir, cleanup_artifact_quarantine, mission_dir, repo_root  # noqa: E402
from train.bc_pretrain import bc_pretrain, resolve_demo_paths  # noqa: E402
from train.checkpointing import (  # noqa: E402
    InterruptHandler,
    LatestCheckpointCallback,
    atomic_save_model,
    checkpoint_zip_path,
    read_sidecar,
    validate_sidecar_n_envs,
    write_sidecar,
)
from train.env_factory import build_vec_env, cleanup_bridge_sessions  # noqa: E402
from train.progress_callback import TrainProgressPctCallback  # noqa: E402

POLICY_KWARGS = {"normalize_images": False}  # obs уже float [0,1], channel-first (4,84,84)


def _default_save_state(mission: Path) -> str:
    manifest = mission / "config" / "playthrough_manifest.yaml"
    if manifest.is_file():
        manifest = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        segments = manifest.get("segments") or []
        if segments:
            return str(segments[0].get("save_state", "states/cp0.fc0"))
    return "states/cp0.fc0"


def load_train_task(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _reward_overrides_from_task(task: dict[str, Any]) -> dict[str, Any] | None:
    hot = task.get("hot_zone")
    if not isinstance(hot, dict):
        return None
    overrides: dict[str, Any] = {"hot_zone": dict(hot)}
    if "milestone_x" in task:
        overrides["milestone_x"] = task["milestone_x"]
    if "milestone_bonus" in task:
        overrides["milestone_bonus"] = task["milestone_bonus"]
    return overrides


def apply_task_defaults(args: argparse.Namespace, task: dict[str, Any], mission: Path) -> None:
    if task.get("checkpoint_in"):
        args.checkpoint_in = str(mission / task["checkpoint_in"])
    if task.get("checkpoint_out"):
        args.checkpoint_out = str(mission / task["checkpoint_out"])
    if task.get("save_state"):
        args.save_state = str(task["save_state"])
    if task.get("reward_profile"):
        args.reward_profile = str(task["reward_profile"])
    if task.get("ppo_timesteps"):
        args.timesteps = int(task["ppo_timesteps"])
    if task.get("learning_rate"):
        args.learning_rate = float(task["learning_rate"])
    if task.get("bc_epochs") is not None:
        args.bc_epochs = int(task["bc_epochs"])
    if task.get("demo_segment"):
        args.bc_demo = str(mission / task["demo_segment"])


def _resolve_checkpoint(path: str | None, mission: Path) -> Path | None:
    if not path:
        return None
    p = Path(path)
    if not p.is_absolute():
        p = mission / p
    return p


def _configure_smoke(args: argparse.Namespace, mission: Path) -> str | None:
    """Smoke: checkpoint в tmp/smoke/<session>/; без runs/ и resume."""
    if not args.smoke:
        return None
    session = (args.smoke_session or "train_smoke").strip() or "train_smoke"
    smoke_dir = artifact_quarantine_dir("smoke", session).resolve()
    if args.checkpoint_out:
        explicit = _resolve_checkpoint(args.checkpoint_out, mission)
        if explicit and mission.resolve() in explicit.resolve().parents:
            print(f"smoke: ignore --checkpoint-out under mission ({explicit})")
    args.checkpoint_out = str(smoke_dir / "checkpoint.zip")
    args.resume = False
    args.no_intermediate_checkpoints = True
    args.latest_checkpoint = False
    print(f"smoke: session={session} checkpoint={args.checkpoint_out}")
    return session


def _persist_train_state(
    model: PPO,
    checkpoint_out: Path,
    *,
    target_timesteps: int,
    game: str,
    mission_id: str,
    n_envs: int,
    save_state: str,
    reason: str,
) -> None:
    atomic_save_model(model, checkpoint_out)
    sidecar = write_sidecar(
        checkpoint_out,
        target_timesteps=target_timesteps,
        game=game,
        mission=mission_id,
        n_envs=n_envs,
        save_state=save_state,
        num_timesteps=int(model.num_timesteps),
    )
    print(f"saved ({reason}) {checkpoint_zip_path(checkpoint_out)}  timesteps={model.num_timesteps}")
    print(f"  sidecar {sidecar.name}")


def train(args: argparse.Namespace) -> Path:
    mission = mission_dir(args.game, args.mission)
    smoke_session: str | None = None
    try:
        task: dict[str, Any] = {}
        if args.task:
            task_path = Path(args.task)
            if not task_path.is_absolute():
                task_path = repo_root() / task_path
            task = load_train_task(task_path)
            apply_task_defaults(args, task, mission)

        smoke_session = _configure_smoke(args, mission)

        save_state = args.save_state or _default_save_state(mission)
        checkpoint_out = _resolve_checkpoint(
            args.checkpoint_out, mission
        ) or (mission / "checkpoints" / "m1_v0.zip")
        checkpoint_out.parent.mkdir(parents=True, exist_ok=True)
        target_timesteps = int(args.timesteps)

        reward_overrides = _reward_overrides_from_task(task)

        torch.set_num_threads(args.threads)
        cleanup_bridge_sessions("train_")

        vec_env = build_vec_env(
            game_id=args.game,
            mission_id=args.mission,
            n_envs=args.n_envs,
            save_state=save_state,
            reward_profile=args.reward_profile,
            reward_overrides=reward_overrides,
            turbo=not args.no_turbo,
            subproc=not args.dummy_vec,
        )

        checkpoint_in = _resolve_checkpoint(args.checkpoint_in, mission)
        resuming = False
        skip_bc = False

        if args.resume and checkpoint_out.is_file():
            sidecar = read_sidecar(checkpoint_out)
            if sidecar:
                validate_sidecar_n_envs(sidecar, args.n_envs)
                target_timesteps = int(sidecar.get("target_timesteps", target_timesteps))
            print(f"resume checkpoint {checkpoint_out}  target={target_timesteps}")
            model = PPO.load(str(checkpoint_out.with_suffix("")), env=vec_env, device="cpu")
            model.learning_rate = args.learning_rate
            resuming = True
            skip_bc = True
        elif checkpoint_in and checkpoint_in.is_file():
            print(f"load checkpoint {checkpoint_in}")
            model = PPO.load(str(checkpoint_in.with_suffix("")), env=vec_env, device="cpu")
            model.learning_rate = args.learning_rate
        else:
            print("new PPO CnnPolicy")
            model = PPO(
                "CnnPolicy",
                vec_env,
                learning_rate=args.learning_rate,
                n_steps=args.n_steps,
                batch_size=args.batch_size,
                n_epochs=args.n_epochs,
                gamma=args.gamma,
                policy_kwargs=POLICY_KWARGS,
                verbose=1,
                device="cpu",
            )

        if not skip_bc and not args.no_bc and args.bc_epochs > 0:
            demo_paths = resolve_demo_paths(mission, args.bc_demo)
            bc_pretrain(
                model,
                mission,
                demo_paths=demo_paths,
                epochs=args.bc_epochs,
                batch_size=args.batch_size,
                learning_rate=min(args.learning_rate, 1e-4),
            )

        write_sidecar(
            checkpoint_out,
            target_timesteps=target_timesteps,
            game=args.game,
            mission=args.mission,
            n_envs=args.n_envs,
            save_state=save_state,
            num_timesteps=int(model.num_timesteps),
        )

        remaining = target_timesteps - int(model.num_timesteps)
        if remaining <= 0:
            print(f"target already reached ({model.num_timesteps}/{target_timesteps})")
            try:
                vec_env.close()
            except (EOFError, BrokenPipeError):
                pass
            cleanup_bridge_sessions("train_")
            return checkpoint_zip_path(checkpoint_out)

        callbacks: list[Any] = []
        if not args.no_intermediate_checkpoints:
            ckpt_dir = mission / "checkpoints" / "runs"
            ckpt_dir.mkdir(parents=True, exist_ok=True)
            prefix = checkpoint_out.stem
            save_freq = max(args.save_every // args.n_envs, 1)
            callbacks.append(
                CheckpointCallback(
                    save_freq=save_freq,
                    save_path=str(ckpt_dir),
                    name_prefix=prefix,
                    save_replay_buffer=False,
                    save_vecnormalize=False,
                )
            )
        if args.latest_checkpoint:
            latest = mission / "checkpoints" / "latest.zip"
            callbacks.append(LatestCheckpointCallback(latest))
        if not args.no_progress_pct and not args.progress:
            callbacks.append(TrainProgressPctCallback(target_timesteps))

        print(
            f"train: game={args.game} mission={args.mission} "
            f"n_envs={args.n_envs} remaining={remaining}/{target_timesteps} "
            f"save_state={save_state} resume={resuming}"
        )

        with InterruptHandler() as interrupt:
            try:
                model.learn(
                    total_timesteps=remaining,
                    callback=CallbackList(callbacks) if callbacks else None,
                    progress_bar=args.progress,
                    reset_num_timesteps=not resuming,
                )
            finally:
                try:
                    vec_env.close()
                except (EOFError, BrokenPipeError):
                    pass
                cleanup_bridge_sessions("train_")
                if int(model.num_timesteps) > 0:
                    _persist_train_state(
                        model,
                        checkpoint_out,
                        target_timesteps=target_timesteps,
                        game=args.game,
                        mission_id=args.mission,
                        n_envs=args.n_envs,
                        save_state=save_state,
                        reason="interrupt" if interrupt.interrupted else "complete",
                    )

        return checkpoint_zip_path(checkpoint_out)
    finally:
        if smoke_session is not None:
            cleanup_artifact_quarantine("smoke", smoke_session)
            print(f"smoke: cleaned tmp/smoke/{smoke_session}/")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="PPO train (CPU, FCEUX env)")
    p.add_argument("--game", default="rushn_attack")
    p.add_argument("--mission", default="m1")
    p.add_argument("--task", help="tasks/train_task.json (finetune / overrides)")
    p.add_argument("--timesteps", type=int, default=500_000)
    p.add_argument("--n-envs", type=int, default=8)
    p.add_argument("--n-steps", type=int, default=128)
    p.add_argument("--batch-size", type=int, default=256)
    p.add_argument("--n-epochs", type=int, default=4)
    p.add_argument("--gamma", type=float, default=0.99)
    p.add_argument("--learning-rate", type=float, default=2.5e-4)
    p.add_argument("--save-every", type=int, default=50_000, help="checkpoint каждые N env steps (total)")
    p.add_argument("--threads", type=int, default=2, help="torch.set_num_threads")
    p.add_argument("--save-state", default=None, help="states/cp0.fc0 относительно миссии")
    p.add_argument("--reward-profile", default="default")
    p.add_argument("--checkpoint-in", default=None)
    p.add_argument("--checkpoint-out", default=None)
    p.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="продолжить checkpoint_out + sidecar (default: on)",
    )
    p.add_argument(
        "--latest-checkpoint",
        action="store_true",
        help="дополнительно писать checkpoints/latest.zip на каждый rollout",
    )
    p.add_argument("--bc-demo", default=None, help="demos/seg_XXX.npz для BC")
    p.add_argument("--bc-epochs", type=int, default=0, help="BC epochs (0 = skip)")
    p.add_argument("--no-bc", action="store_true")
    p.add_argument("--no-turbo", action="store_true", help="FCEUX без turbo (отладка)")
    p.add_argument("--progress", action="store_true", help="progress bar (needs tqdm+rich)")
    p.add_argument(
        "--no-progress-pct",
        action="store_true",
        help="не печатать train: N%% (done/target steps) в stderr",
    )
    p.add_argument("--dummy-vec", action="store_true", help="DummyVecEnv вместо SubprocVecEnv")
    p.add_argument(
        "--smoke",
        action="store_true",
        help="короткий train: checkpoint в tmp/smoke/<session>/, autodelete в finally",
    )
    p.add_argument(
        "--smoke-session",
        default="train_smoke",
        help="подкаталог tmp/smoke/ при --smoke (default: train_smoke)",
    )
    p.add_argument(
        "--no-intermediate-checkpoints",
        action="store_true",
        help="без CheckpointCallback / checkpoints/runs/ (включено при --smoke)",
    )
    return p


def main() -> None:
    args = build_parser().parse_args()
    train(args)


if __name__ == "__main__":
    main()
