"""Локальный inference: model.predict() + logs/YYYYMMDD_*.jsonl + playlist."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from stable_baselines3 import PPO

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "src"))

from achievements.evaluator import (  # noqa: E402
    evaluate_records,
    load_achievements_config,
    overlay_payload,
    write_tagged_attempts,
)
from achievements.playlist import build_playlist  # noqa: E402
from attempt_logger import AttemptLogger  # noqa: E402
from env.loader import make_env  # noqa: E402
from fceux_launch import load_fceux_profile  # noqa: E402
from inference_states import resolve_inference_reset_state  # noqa: E402
from inference_input_logger import InferenceInputLogger  # noqa: E402
from jsonl_logs import dated_log_path, load_jsonl_window, utc_date_prefix  # noqa: E402
from project_paths import mission_dir, repo_root  # noqa: E402


def _overlay_path(session_id: str) -> Path:
    return repo_root() / "tmp" / "bridge" / session_id / "overlay.json"


def _write_overlay(session_id: str, payload: dict) -> None:
    path = _overlay_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_episode_overlay(logs_dir: Path, date_prefix: str, episode: int, payload: dict) -> Path:
    path = logs_dir / f"{date_prefix}_ep{episode:04d}.overlay.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_inference(args: argparse.Namespace) -> None:
    if not args.skip_preflight:
        from inference_preflight import require_inference_preflight  # noqa: WPS433

        require_inference_preflight(
            game=args.game,
            mission=args.mission,
            clean_logs=True,
            label="run_inference",
        )

    mission = mission_dir(args.game, args.mission)
    checkpoint = Path(args.checkpoint)
    if not checkpoint.is_absolute():
        candidate = mission / checkpoint
        checkpoint = candidate if candidate.is_file() else mission / "checkpoints" / checkpoint
    if not checkpoint.is_file() and not str(checkpoint).endswith(".zip"):
        checkpoint = checkpoint.with_suffix(".zip")
    if not checkpoint.is_file():
        raise SystemExit(f"Checkpoint not found: {checkpoint}")

    save_state = args.save_state
    if not save_state:
        try:
            save_state = resolve_inference_reset_state(mission, cp_index=0)
        except FileNotFoundError as exc:
            raise SystemExit(str(exc)) from exc
        if not (mission / save_state).is_file():
            raise SystemExit(
                f"Inference save state not found: {mission / save_state}. "
                "Run scripts/build_inference_states.py"
            )

    profile = load_fceux_profile(args.fceux_profile)
    show_window = args.show_window or not bool(profile.get("headless", True))
    turbo = profile.get("turbo", False) if args.turbo is None else args.turbo

    model_version = args.model_version or checkpoint.stem
    logs_dir = mission / "logs"
    attempt_logger = AttemptLogger(logs_dir)
    input_logger = InferenceInputLogger(logs_dir)
    achievements_cfg = load_achievements_config()

    env = make_env(
        args.game,
        args.mission,
        session_id=args.session,
        save_state=save_state,
        turbo=turbo,
        reward_profile=args.reward_profile,
        show_window=show_window,
    )
    model = PPO.load(str(checkpoint.with_suffix("")), device="cpu")

    date_prefix = utc_date_prefix()

    try:
        for ep in range(1, args.episodes + 1):
            obs, info = env.reset()
            input_logger.begin_episode(ep)
            done = False
            last_info = info
            steps = 0

            while not done and steps < args.max_steps:
                action, _ = model.predict(obs, deterministic=not args.stochastic)
                obs, _reward, terminated, truncated, info = env.step(int(action))
                last_info = info
                steps += 1
                done = terminated or truncated

                action_str = info.get("action", "")
                frame = int((info.get("ram") or {}).get("frame", 0))
                input_logger.log_step(step=steps - 1, frame=frame, action=action_str)

            record = attempt_logger.log_episode(
                mission=args.mission.replace("m", ""),
                episode=ep,
                info=last_info,
                model_version=model_version,
                save_state=save_state,
                inference_inputs_ref=input_logger.log_path.name,
            )

            history = load_jsonl_window(attempt_logger.log_path)
            tagged = evaluate_records(history, achievements_cfg)
            write_tagged_attempts(attempt_logger.log_path, tagged)
            record = next((r for r in tagged if r.get("episode") == ep), record)

            overlay = overlay_payload(record, config=achievements_cfg)
            _write_overlay(args.session, overlay)
            ep_overlay = _write_episode_overlay(logs_dir, date_prefix, ep, overlay)

            print(
                f"episode {ep}: steps={steps} max_cp={last_info.get('max_checkpoint')} "
                f"reward={last_info.get('episode_reward', 0):.2f} died={last_info.get('died')} "
                f"tags={record.get('tags', [])}"
            )
            print(f"  overlay: {ep_overlay}")

        if args.build_playlist:
            created, manifest_path, clip_count = build_playlist(
                attempt_logger.log_path,
                logs_dir,
                config=achievements_cfg,
                inference_inputs_path=input_logger.log_path,
                game=args.game,
                mission=args.mission,
                dedupe=not args.playlist_no_dedupe,
            )
            if manifest_path:
                print(f"playlist manifest: {manifest_path} ({clip_count} clips)")
                print(f"playlist launcher: {manifest_path.with_suffix('.play.cmd')}")
            else:
                print("playlist: no clips matched nominations")
            print(f"playlist blocks: {len(created)} slug(s), {sum(len(v) for v in created.values())} clips")

    finally:
        env.close()

    print(f"logged {attempt_logger.log_path}")
    print(f"inputs {input_logger.log_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Local PPO inference")
    parser.add_argument("--game", default="rushn_attack")
    parser.add_argument("--mission", default="m1")
    parser.add_argument("--checkpoint", default="m1_v0.zip", help="checkpoints/m1_v0.zip или имя файла")
    parser.add_argument("--episodes", type=int, default=5)
    parser.add_argument("--max-steps", type=int, default=8000)
    parser.add_argument("--save-state", default=None)
    parser.add_argument("--reward-profile", default="default")
    parser.add_argument("--model-version", default=None)
    parser.add_argument("--session", default="inference")
    parser.add_argument("--stochastic", action="store_true")
    parser.add_argument("--fceux-profile", default="inference", help="fceux/profiles/{name}.yaml")
    parser.add_argument("--show-window", action="store_true", help="видимое окно FCEUX")
    parser.add_argument("--turbo", action="store_true", default=None, help="override turbo из профиля")
    parser.add_argument("--build-playlist", action="store_true", help="собрать плейлист после прогона")
    parser.add_argument(
        "--playlist-no-dedupe",
        action="store_true",
        help="плейлист без дедупликации одинаковых эпизодов",
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="не вызывать inference_preflight (inference_local.sh чистит отдельно)",
    )
    args = parser.parse_args()
    run_inference(args)


if __name__ == "__main__":
    main()
