"""Локальный inference: два сценария — pool (пул + плейлист) и live (эфир до Ctrl+C)."""
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
from inference_input_logger import InferenceInputLogger  # noqa: E402
from inference_states import resolve_inference_reset_state  # noqa: E402
from jsonl_logs import (  # noqa: E402
    load_jsonl,
    next_episode_number,
    normalize_model_version,
    require_consistent_model_version,
)
from project_paths import (  # noqa: E402
    add_game_mission_arguments,
    apply_resolved_game_mission,
    mission_dir,
    repo_root,
)
from train.phase_aware_ppo import PhaseAwarePPO  # noqa: E402
from train.phase_heads import (  # noqa: E402
    load_policy_heads_spec,
    predict_with_phase,
    resolve_model_zip,
)

DEFAULT_PLAYLIST_CNT = 5


def validate_inference_args(
    args: argparse.Namespace,
    *,
    argv: list[str] | None = None,
) -> None:
    """Взаимоисключение pool vs live (два операторских сценария)."""
    if not bool(getattr(args, "live", False)):
        return
    conflicts: list[str] = []
    argv_list = list(sys.argv[1:] if argv is None else argv)
    if "--playlist-cnt" in argv_list:
        conflicts.append("--playlist-cnt")
    if bool(getattr(args, "playlist_no_dedupe", False)):
        conflicts.append("--playlist-no-dedupe")
    if bool(getattr(args, "wipe_gen_logs", False)):
        conflicts.append("--wipe-gen-logs")
    if conflicts:
        raise SystemExit(
            "--live — сценарий эфира без пула/плейлиста; "
            f"уберите: {', '.join(conflicts)}"
        )


def _overlay_path(session_id: str) -> Path:
    return repo_root() / "tmp" / "bridge" / session_id / "overlay.json"


def _write_overlay(session_id: str, payload: dict) -> None:
    path = _overlay_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


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


def _load_model(args: argparse.Namespace, model_path: Path) -> tuple[Any, Any]:
    heads_spec = load_policy_heads_spec(args.game)
    if heads_spec is None:
        model = PPO.load(str(model_path.with_suffix("")), device="cpu")
        return model, heads_spec
    try:
        model = PhaseAwarePPO.load(str(model_path.with_suffix("")), device="cpu")
    except Exception as exc:
        raise SystemExit(
            f"policy_heads is set in env_config but model is not Multi-head PhaseAwarePPO: {exc}. "
            "Train a new genN with Multi-head (no single-head CnnPolicy fallback)."
        ) from exc
    if not hasattr(model.policy, "set_active_head"):
        raise SystemExit(
            "policy_heads is set but loaded policy has no set_active_head; "
            "train a Multi-head genN"
        )
    model.heads_spec = heads_spec
    return model, heads_spec


def _resolve_save_state(args: argparse.Namespace, mission: Path) -> str:
    save_state = args.save_state
    if save_state:
        return save_state
    try:
        save_state = resolve_inference_reset_state(mission)
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc
    if not (mission / save_state).is_file():
        raise SystemExit(
            f"Inference save state not found: {mission / save_state}. "
            "Run: scripts/build_playthrough.py … --states-only"
        )
    return save_state


def _make_inference_env(
    args: argparse.Namespace,
    *,
    save_state: str,
    show_window: bool,
    turbo: bool,
) -> Any:
    return make_env(
        args.game,
        args.mission,
        session_id=args.session,
        save_state=save_state,
        turbo=turbo,
        reward_profile=args.reward_profile,
        show_window=show_window,
    )


def _play_episode_steps(
    *,
    env: Any,
    model: PPO,
    heads_spec: Any,
    args: argparse.Namespace,
    input_logger: InferenceInputLogger | None,
    ep: int,
) -> tuple[dict[str, Any], int, set[str], int]:
    """Один эпизод: predict/step. Опционально пишет inference_inputs."""
    obs, info = env.reset()
    if input_logger is not None:
        input_logger.begin_episode(ep)
    done = False
    last_info = info
    steps = 0
    heads_used: set[str] = set()
    prev_head_id: str | None = None
    head_switches = 0

    while not done and steps < args.max_steps:
        phase_id = info.get("phase_id")
        action, _, head_id = predict_with_phase(
            model, obs, phase_id, heads_spec, deterministic=not args.stochastic
        )
        heads_used.add(head_id)
        if prev_head_id is not None and head_id != prev_head_id:
            head_switches += 1
        prev_head_id = head_id

        obs, _reward, terminated, truncated, info = env.step(int(action))
        last_info = info
        steps += 1
        done = terminated or truncated

        action_str = info.get("action", "")
        frame = int((info.get("ram") or {}).get("frame", 0))
        if input_logger is not None:
            input_logger.log_step(step=steps - 1, frame=frame, action=action_str)

    return last_info, steps, heads_used, head_switches


def _run_pool_episode(
    *,
    env: Any,
    model: PPO,
    heads_spec: Any,
    ep: int,
    args: argparse.Namespace,
    save_state: str,
    attempt_logger: AttemptLogger,
    input_logger: InferenceInputLogger,
    achievements_cfg: dict[str, Any],
    model_version: str,
) -> None:
    last_info, steps, heads_used, head_switches = _play_episode_steps(
        env=env,
        model=model,
        heads_spec=heads_spec,
        args=args,
        input_logger=input_logger,
        ep=ep,
    )

    record = attempt_logger.log_episode(
        mission=args.mission.replace("m", ""),
        episode=ep,
        info=last_info,
        model_version=model_version,
        save_state=save_state,
        inference_inputs_ref=input_logger.log_path.name,
    )

    history = load_jsonl(attempt_logger.log_path)
    tagged = evaluate_records(history, achievements_cfg)
    write_tagged_attempts(attempt_logger.log_path, tagged)
    record = next((r for r in tagged if r.get("episode") == ep), record)

    overlay = overlay_payload(record, config=achievements_cfg)
    _write_overlay(args.session, overlay)

    print(
        f"episode {ep}: steps={steps} max_cp={last_info.get('max_checkpoint')} "
        f"reward={last_info.get('episode_reward', 0):.2f} died={last_info.get('died')} "
        f"tags={record.get('tags', [])} "
        f"heads={sorted(heads_used)} switches={head_switches} "
        f"end_phase={last_info.get('phase_id')}"
    )


def _run_live_episode(
    *,
    env: Any,
    model: PPO,
    heads_spec: Any,
    ep: int,
    args: argparse.Namespace,
) -> None:
    """Эфирный прогон без записи в logs/genN/."""
    last_info, steps, heads_used, head_switches = _play_episode_steps(
        env=env,
        model=model,
        heads_spec=heads_spec,
        args=args,
        input_logger=None,
        ep=ep,
    )
    print(
        f"live episode {ep}: steps={steps} max_cp={last_info.get('max_checkpoint')} "
        f"reward={last_info.get('episode_reward', 0):.2f} died={last_info.get('died')} "
        f"heads={sorted(heads_used)} switches={head_switches} "
        f"end_phase={last_info.get('phase_id')}"
    )


def _run_pool_inference(
    args: argparse.Namespace,
    *,
    mission: Path,
    model_path: Path,
    model_version: str,
    save_state: str,
) -> None:
    profile = load_fceux_profile(args.fceux_profile)
    show_window = not bool(profile.get("headless", True))
    turbo = profile.get("turbo", False) if args.turbo is None else args.turbo

    model, heads_spec = _load_model(args, model_path)
    logs_dir = mission / "logs"
    attempt_logger = AttemptLogger(logs_dir, model_version=model_version)
    input_logger = InferenceInputLogger(logs_dir, model_version=model_version)
    achievements_cfg = load_achievements_config(game_id=args.game)
    playlist_cnt = args.playlist_cnt
    if playlist_cnt is None:
        playlist_cnt = DEFAULT_PLAYLIST_CNT
    batch_size = max(1, int(playlist_cnt))
    dedupe = not args.playlist_no_dedupe
    next_ep = next_episode_number(attempt_logger.log_path)

    env = _make_inference_env(
        args, save_state=save_state, show_window=show_window, turbo=bool(turbo)
    )
    try:
        for offset in range(batch_size):
            _run_pool_episode(
                env=env,
                model=model,
                heads_spec=heads_spec,
                ep=next_ep + offset,
                args=args,
                save_state=save_state,
                attempt_logger=attempt_logger,
                input_logger=input_logger,
                achievements_cfg=achievements_cfg,
                model_version=model_version,
            )
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


def _run_live_inference(
    args: argparse.Namespace,
    *,
    mission: Path,
    model_path: Path,
    save_state: str,
) -> None:
    profile = load_fceux_profile(args.fceux_profile)
    # Live всегда с окном; turbo выкл по умолчанию (иначе часто серое окно).
    turbo = False if args.turbo is None else bool(args.turbo)
    model, heads_spec = _load_model(args, model_path)
    env = _make_inference_env(
        args, save_state=save_state, show_window=True, turbo=turbo
    )
    print(
        "live: окно FCEUX, без записи logs/genN/; стоп — Ctrl+C",
        flush=True,
    )
    ep = 1
    try:
        while True:
            _run_live_episode(
                env=env,
                model=model,
                heads_spec=heads_spec,
                ep=ep,
                args=args,
            )
            ep += 1
    except KeyboardInterrupt:
        print(f"live stopped after {ep - 1} episode(s)", flush=True)
    finally:
        env.close()


def run_inference(args: argparse.Namespace) -> None:
    validate_inference_args(args)

    mission = mission_dir(args.game, args.mission)
    try:
        model_path = resolve_model_zip(mission, args.model)
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc

    require_consistent_model_version(model=args.model, model_version=args.model_version)
    model_version = normalize_model_version(args.model_version or model_path.stem)

    if args.skip_preflight and getattr(args, "wipe_gen_logs", False):
        raise SystemExit(
            "--wipe-gen-logs нельзя с --skip-preflight "
            "(wipe в preflight; уберите --skip-preflight или wipe)"
        )

    if not args.skip_preflight:
        from inference_preflight import require_inference_preflight  # noqa: WPS433

        require_inference_preflight(
            game=args.game,
            mission=args.mission,
            model_version=model_version,
            clean_logs=bool(getattr(args, "wipe_gen_logs", False)),
            label="run_inference",
        )

    save_state = _resolve_save_state(args, mission)

    if args.live:
        _run_live_inference(
            args,
            mission=mission,
            model_path=model_path,
            save_state=save_state,
        )
        return

    _run_pool_inference(
        args,
        mission=mission,
        model_path=model_path,
        model_version=model_version,
        save_state=save_state,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Local PPO inference. "
            "Pool: --playlist-cnt N -> logs/genN/ + playlist. "
            "Live: --live until Ctrl+C (window, no pool)."
        )
    )
    add_game_mission_arguments(parser)
    parser.add_argument("--model", default="gen0.zip", help="models/gen0.zip или имя файла")
    parser.add_argument(
        "--playlist-cnt",
        type=int,
        default=None,
        help=(
            f"pool: число попыток перед сборкой плейлиста "
            f"(default {DEFAULT_PLAYLIST_CNT}; нельзя с --live)"
        ),
    )
    parser.add_argument("--max-steps", type=int, default=8000)
    parser.add_argument("--save-state", default=None)
    parser.add_argument("--reward-profile", default="default")
    parser.add_argument("--model-version", default=None)
    parser.add_argument("--session", default="inference")
    parser.add_argument("--stochastic", action="store_true")
    parser.add_argument("--fceux-profile", default="inference", help="fceux/profiles/{name}.yaml")
    parser.add_argument(
        "--live",
        action="store_true",
        help="эфир: окно FCEUX до Ctrl+C, без записи logs/genN/",
    )
    parser.add_argument(
        "--turbo",
        action="store_true",
        default=None,
        help="force turbo on (pool: из inference.yaml; live: по умолчанию выкл)",
    )
    parser.add_argument(
        "--playlist-no-dedupe",
        action="store_true",
        help="pool: плейлист без дедупликации (нельзя с --live)",
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="не вызывать inference_preflight (inference_local.sh чистит отдельно)",
    )
    parser.add_argument(
        "--wipe-gen-logs",
        action="store_true",
        help="pool: удалить logs/<model_version>/ перед сбором (нельзя с --live)",
    )
    args = parser.parse_args()
    apply_resolved_game_mission(args)
    run_inference(args)


if __name__ == "__main__":
    main()
