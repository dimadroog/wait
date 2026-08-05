"""Сбор argv для subprocess-фасадов лаунчера (Python, без bash/WSL)."""
from __future__ import annotations

import sys
from pathlib import Path

from project_paths import repo_root

from operator_launcher.catalog import model_out_rel


def venv_python() -> str:
    root = repo_root()
    win = root / ".venv" / "Scripts" / "python.exe"
    if win.is_file():
        return str(win)
    unix = root / ".venv" / "bin" / "python"
    if unix.is_file():
        return str(unix)
    return sys.executable


def _py() -> str:
    return venv_python()


def _context_args(game: str, mission: str, save_state: str) -> list[str]:
    return [
        "--game",
        game,
        "--mission",
        mission,
        "--save-state",
        save_state,
    ]


def build_inference_preflight_argv(
    *,
    game: str,
    mission: str,
    model: str,
    wipe_gen_logs: bool = False,
) -> list[str]:
    argv = [
        _py(),
        "scripts/inference_preflight.py",
        "--game",
        game,
        "--mission",
        mission,
        "--model",
        model,
    ]
    if wipe_gen_logs:
        argv.append("--wipe-gen-logs")
    return argv


def build_inference_run_argv(
    *,
    game: str,
    mission: str,
    save_state: str,
    model: str,
    live: bool,
    stochastic: bool,
    max_steps: int,
    turbo: bool,
    reward_profile: str,
    playlist_cnt: int | None = None,
    wipe_gen_logs: bool = False,
    playlist_no_dedupe: bool = False,
) -> list[str]:
    argv = [
        _py(),
        "src/stream/run_inference.py",
        "--skip-preflight",
        "--model",
        model,
        "--max-steps",
        str(max_steps),
        "--reward-profile",
        reward_profile,
        *_context_args(game, mission, save_state),
    ]
    if live:
        argv.append("--live")
        if stochastic:
            argv.append("--stochastic")
    else:
        if playlist_cnt is not None:
            argv.extend(["--playlist-cnt", str(playlist_cnt)])
        if stochastic:
            argv.append("--stochastic")
        if wipe_gen_logs:
            argv.append("--wipe-gen-logs")
        if playlist_no_dedupe:
            argv.append("--playlist-no-dedupe")
    if turbo:
        argv.append("--turbo")
    return argv


def build_inference_live_phases(
    *,
    game: str,
    mission: str,
    save_state: str,
    model: str,
    stochastic: bool,
    max_steps: int,
    turbo: bool,
    reward_profile: str,
) -> list[list[str]]:
    """Эквивалент inference_local.sh --live (preflight → run_inference)."""
    return [
        build_inference_preflight_argv(game=game, mission=mission, model=model),
        build_inference_run_argv(
            game=game,
            mission=mission,
            save_state=save_state,
            model=model,
            live=True,
            stochastic=stochastic,
            max_steps=max_steps,
            turbo=turbo,
            reward_profile=reward_profile,
        ),
    ]


def build_inference_pool_phases(
    *,
    game: str,
    mission: str,
    save_state: str,
    model: str,
    playlist_cnt: int,
    stochastic: bool,
    max_steps: int,
    wipe_gen_logs: bool,
    playlist_no_dedupe: bool,
    reward_profile: str,
) -> list[list[str]]:
    """Эквивалент inference_local.sh pool (preflight → run_inference)."""
    return [
        build_inference_preflight_argv(
            game=game,
            mission=mission,
            model=model,
            wipe_gen_logs=wipe_gen_logs,
        ),
        build_inference_run_argv(
            game=game,
            mission=mission,
            save_state=save_state,
            model=model,
            live=False,
            stochastic=stochastic,
            max_steps=max_steps,
            turbo=False,
            reward_profile=reward_profile,
            playlist_cnt=playlist_cnt,
            wipe_gen_logs=wipe_gen_logs,
            playlist_no_dedupe=playlist_no_dedupe,
        ),
    ]


def build_inference_replay_argv(
    *,
    game: str,
    mission: str,
    input_path: str,
    turbo: bool,
    timeout: float,
) -> list[str]:
    argv = [
        _py(),
        "scripts/play_inference_fm2.py",
        input_path,
        "--game",
        game,
        "--mission",
        mission,
        "--timeout",
        str(timeout),
    ]
    if turbo:
        argv.append("--turbo")
    return argv


def build_editorial_playlist_argv(
    *,
    game: str,
    mission: str,
    model: str,
    max_airtime: str | None = None,
    max_clips: int | None = None,
    max_per_slug: int | None = None,
    no_dedupe: bool = False,
) -> list[str]:
    argv = [
        _py(),
        "scripts/build_playlist.py",
        "--editorial",
        "--model",
        model,
        "--game",
        game,
        "--mission",
        mission,
    ]
    if max_airtime:
        argv.extend(["--max-airtime", max_airtime])
    if max_clips is not None:
        argv.extend(["--max-clips", str(max_clips)])
    if max_per_slug is not None:
        argv.extend(["--max-per-slug", str(max_per_slug)])
    if no_dedupe:
        argv.append("--no-dedupe")
    return argv


def build_train_phases(
    *,
    game: str,
    mission: str,
    save_state: str,
    train_mode: str,
    model_out: str,
    model_in: str | None,
    timesteps: int,
    n_envs: int,
    bc_epochs: int,
    bc_demo: str | None,
    reward_profile: str,
    progress_pct: bool,
    save_every: int,
    latest_model: bool,
    latest_every: int,
) -> list[list[str]]:
    """Эквивалент train_local.sh (preflight → train_ppo)."""
    if bc_epochs > 0 and not (bc_demo or "").strip():
        raise ValueError(
            "При bc_epochs > 0 нужно указать bc_demo; "
            "пустое значение подхватывает все сегменты demos_for_bc"
        )
    train_argv = [
        _py(),
        "src/train/train_ppo.py",
        "--n-envs",
        str(n_envs),
        "--model-out",
        model_out_rel(model_out),
        "--timesteps",
        str(timesteps),
        "--reward-profile",
        reward_profile,
        "--save-every",
        str(save_every),
        "--latest-every",
        str(latest_every),
        *_context_args(game, mission, save_state),
    ]
    if train_mode == "scratch":
        train_argv.append("--scratch")
    elif train_mode == "from_ancestor":
        if not model_in:
            raise ValueError("from_ancestor requires model_in")
        train_argv.extend(["--model-in", model_out_rel(model_in)])
    elif train_mode == "rollback":
        raise ValueError("use build_train_rollback_phases for rollback")
    if bc_epochs > 0:
        train_argv.extend(["--bc-epochs", str(bc_epochs)])
    if bc_demo:
        train_argv.extend(["--bc-demo", bc_demo])
    if not progress_pct:
        train_argv.append("--no-progress-pct")
    if latest_model:
        train_argv.append("--latest-model")
    else:
        train_argv.append("--no-latest-model")
    return [[_py(), "scripts/train_preflight.py"], train_argv]


def build_train_rollback_phases(
    *,
    game: str,
    mission: str,
    model_out: str,
) -> list[list[str]]:
    return [
        [_py(), "scripts/train_preflight.py"],
        [
            _py(),
            "src/train/train_ppo.py",
            "--n-envs",
            "6",
            "--rollback",
            "--model-out",
            model_out_rel(model_out),
            "--game",
            game,
            "--mission",
            mission,
        ],
    ]


def format_argv_for_shell(argv: list[str] | list[list[str]]) -> str:
    """Однострочная команда для копирования в терминал (из корня репо)."""
    py = Path(venv_python()).name
    if argv and isinstance(argv[0], list):
        return " && ".join(format_argv_for_shell(phase) for phase in argv)
    parts: list[str] = []
    for i, arg in enumerate(argv):
        text = str(arg)
        if i == 0 and text.endswith("python.exe"):
            parts.append(f".venv/Scripts/{py}")
            continue
        if Path(text).is_absolute():
            try:
                text = str(Path(text).relative_to(repo_root()))
            except ValueError:
                pass
        text = text.replace("\\", "/")
        if " " in text:
            parts.append(f'"{text}"')
        else:
            parts.append(text)
    return " ".join(parts)


def format_argv(argv: list[str] | list[list[str]]) -> str:
    if argv and isinstance(argv[0], list):
        return " && ".join(format_argv(phase) for phase in argv)
    root = repo_root()
    parts: list[str] = []
    for arg in argv:
        text = str(arg)
        if Path(text).is_absolute() and str(root) in text:
            try:
                text = str(Path(text).relative_to(root))
            except ValueError:
                pass
        if " " in text:
            parts.append(f'"{text}"')
        else:
            parts.append(text)
    return " ".join(parts)
