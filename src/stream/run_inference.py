"""Локальный inference: model.predict() + logs/<model_version>/*.jsonl + playlist."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from stable_baselines3 import PPO

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "src"))

from achievements.airtime import load_playlist_airtime  # noqa: E402
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
from fm2_export import export_episode_fm2_from_steps, write_fm2_sidecar  # noqa: E402
from inference_input_logger import InferenceInputLogger  # noqa: E402
from inference_states import resolve_inference_reset_state  # noqa: E402
from jsonl_logs import gen_pool_dir, normalize_model_version  # noqa: E402
from project_paths import mission_dir, repo_root  # noqa: E402


def _overlay_path(session_id: str) -> Path:
    return repo_root() / "tmp" / "bridge" / session_id / "overlay.json"


def _write_overlay(session_id: str, payload: dict) -> None:
    path = _overlay_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_episode_overlay(pool_dir: Path, episode: int, payload: dict) -> Path:
    path = pool_dir / f"ep{episode:04d}.overlay.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _rebuild_playlist(
    *,
    attempts_path: Path,
    logs_dir: Path,
    achievements_cfg: dict[str, Any],
    inputs_path: Path,
    game: str,
    mission: str,
    dedupe: bool,
    model_version: str,
) -> tuple[Path | None, int, float]:
    created, manifest_path, clip_count = build_playlist(
        attempts_path,
        logs_dir,
        config=achievements_cfg,
        inference_inputs_path=inputs_path if inputs_path.is_file() else None,
        game=game,
        mission=mission,
        dedupe=dedupe,
        model_version=model_version,
    )
    hours = 0.0
    if manifest_path and manifest_path.is_file():
        air = load_playlist_airtime(manifest_path.parent)
        hours = air.hours if air else 0.0
        print(f"playlist manifest: {manifest_path} ({clip_count} clips)")
        print(f"playlist launcher: {manifest_path.with_suffix('.play.cmd')}")
        print(f"playlist airtime={hours * 3600:.1f}s ({hours:.4f}h), clips={clip_count}")
    else:
        print("playlist: no clips matched nominations")
    print(f"playlist blocks: {len(created)} slug(s), {sum(len(v) for v in created.values())} clips")
    return manifest_path, clip_count, hours


def _run_one_episode(
    *,
    env: Any,
    model: PPO,
    ep: int,
    args: argparse.Namespace,
    mission: Path,
    save_state: str,
    pool_dir: Path,
    attempt_logger: AttemptLogger,
    input_logger: InferenceInputLogger,
    achievements_cfg: dict[str, Any],
    model_version: str,
) -> None:
    obs, info = env.reset()
    input_logger.begin_episode(ep)
    done = False
    last_info = info
    steps = 0
    step_log: list[dict] = []

    while not done and steps < args.max_steps:
        action, _ = model.predict(obs, deterministic=not args.stochastic)
        obs, _reward, terminated, truncated, info = env.step(int(action))
        last_info = info
        steps += 1
        done = terminated or truncated

        action_str = info.get("action", "")
        frame = int((info.get("ram") or {}).get("frame", 0))
        input_logger.log_step(step=steps - 1, frame=frame, action=action_str)
        step_log.append({"action": action_str, "frame": frame})

    fm2_path: Path | None = None
    # С плейлистом канон имён — NN_slug_MMM; epNNNN не пишем в logs/genN/.
    write_raw_ep_fm2 = bool(args.save_episode_fm2) and not bool(args.build_playlist)
    if write_raw_ep_fm2:
        save_state_path = mission / save_state
        fm2_path = pool_dir / f"ep{ep:04d}.fm2"
        export_episode_fm2_from_steps(
            step_log,
            fm2_path,
            save_state_path=save_state_path,
            episode=ep,
            game_id=args.game,
            mission_id=args.mission,
        )

    record = attempt_logger.log_episode(
        mission=args.mission.replace("m", ""),
        episode=ep,
        info=last_info,
        model_version=model_version,
        save_state=save_state,
        inference_inputs_ref=input_logger.log_path.name,
    )
    if fm2_path:
        record["fm2_path"] = str(fm2_path.resolve())

    history = load_jsonl(attempt_logger.log_path)
    tagged = evaluate_records(history, achievements_cfg)
    if fm2_path:
        for row in tagged:
            if int(row.get("episode", -1)) == ep:
                row["fm2_path"] = str(fm2_path.resolve())
                break
    write_tagged_attempts(attempt_logger.log_path, tagged)
    record = next((r for r in tagged if r.get("episode") == ep), record)

    overlay = overlay_payload(record, config=achievements_cfg)
    _write_overlay(args.session, overlay)
    if write_raw_ep_fm2:
        ep_overlay = _write_episode_overlay(pool_dir, ep, overlay)
        if fm2_path:
            write_fm2_sidecar(fm2_path, overlay=overlay)
        print(f"  overlay: {ep_overlay}")
        if fm2_path:
            print(f"  fm2: {fm2_path}")
            print(f"  visual: ./.venv/Scripts/python.exe scripts/play_fm2_gui.py {fm2_path.as_posix()}")

    print(
        f"episode {ep}: steps={steps} max_cp={last_info.get('max_checkpoint')} "
        f"reward={last_info.get('episode_reward', 0):.2f} died={last_info.get('died')} "
        f"tags={record.get('tags', [])}"
    )


def run_inference(args: argparse.Namespace) -> None:
    mission = mission_dir(args.game, args.mission)
    model_path = Path(args.model)
    if not model_path.is_absolute():
        candidate = mission / model_path
        model_path = candidate if candidate.is_file() else mission / "models" / model_path
    if not model_path.is_file() and not str(model_path).endswith(".zip"):
        model_path = model_path.with_suffix(".zip")
    if not model_path.is_file():
        raise SystemExit(f"Model not found: {model_path}")

    model_version = normalize_model_version(args.model_version or model_path.stem)

    if not args.skip_preflight:
        from inference_preflight import require_inference_preflight  # noqa: WPS433

        require_inference_preflight(
            game=args.game,
            mission=args.mission,
            model_version=model_version,
            clean_logs=bool(getattr(args, "wipe_gen_logs", False)),
            label="run_inference",
        )

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

    logs_dir = mission / "logs"
    attempt_logger = AttemptLogger(logs_dir, model_version=model_version)
    input_logger = InferenceInputLogger(logs_dir, model_version=model_version)
    achievements_cfg = load_achievements_config()
    pool_dir = gen_pool_dir(logs_dir, model_version)
    batch_size = max(1, int(args.episodes))
    dedupe = not args.playlist_no_dedupe

    env = make_env(
        args.game,
        args.mission,
        session_id=args.session,
        save_state=save_state,
        turbo=turbo,
        reward_profile=args.reward_profile,
        show_window=show_window,
    )
    model = PPO.load(str(model_path.with_suffix("")), device="cpu")

    try:
        next_ep = 1
        for offset in range(batch_size):
            _run_one_episode(
                env=env,
                model=model,
                ep=next_ep + offset,
                args=args,
                mission=mission,
                save_state=save_state,
                pool_dir=pool_dir,
                attempt_logger=attempt_logger,
                input_logger=input_logger,
                achievements_cfg=achievements_cfg,
                model_version=model_version,
            )
        if args.build_playlist:
            _rebuild_playlist(
                attempts_path=attempt_logger.log_path,
                logs_dir=logs_dir,
                achievements_cfg=achievements_cfg,
                inputs_path=input_logger.log_path,
                game=args.game,
                mission=args.mission,
                dedupe=dedupe,
                model_version=model_version,
            )
    finally:
        env.close()

    print(f"logged {attempt_logger.log_path}")
    print(f"inputs {input_logger.log_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Local PPO inference")
    parser.add_argument("--game", default="rushn_attack")
    parser.add_argument("--mission", default="m1")
    parser.add_argument("--model", default="gen0.zip", help="models/gen0.zip или имя файла")
    parser.add_argument(
        "--episodes",
        type=int,
        default=5,
        help="число эпизодов",
    )
    parser.add_argument("--max-steps", type=int, default=8000)
    parser.add_argument("--save-state", default=None)
    parser.add_argument("--reward-profile", default="default")
    parser.add_argument("--model-version", default=None)
    parser.add_argument("--session", default="inference")
    parser.add_argument("--stochastic", action="store_true")
    parser.add_argument("--fceux-profile", default="inference", help="fceux/profiles/{name}.yaml")
    parser.add_argument("--show-window", action="store_true", help="видимое окно FCEUX (default: headless)")
    parser.add_argument("--turbo", action="store_true", default=None, help="force turbo on (в inference.yaml уже true)")
    parser.add_argument("--build-playlist", action="store_true", help="собрать плейлист после прогона")
    parser.add_argument(
        "--playlist-no-dedupe",
        action="store_true",
        help="плейлист без дедупликации одинаковых эпизодов",
    )
    parser.add_argument(
        "--save-episode-fm2",
        action="store_true",
        help="писать logs/<model_version>/epNNNN.fm2 (только без --build-playlist; с плейлистом — NN_slug_MMM)",
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="не вызывать inference_preflight (inference_local.sh чистит отдельно)",
    )
    parser.add_argument(
        "--wipe-gen-logs",
        action="store_true",
        help="перед сбором удалить logs/<model_version>/ (default: keep + учесть airtime)",
    )
    args = parser.parse_args()
    run_inference(args)


if __name__ == "__main__":
    main()
