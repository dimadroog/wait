"""Фабрика vec-env для SubprocVecEnv (pickle-safe на Windows)."""
from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Any

from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv, VecEnv

from project_paths import repo_root


def kill_orphan_fceux_bridge() -> None:
    """Завершить headless FCEUX (bridge.lua) после аварийного train/record."""
    if sys.platform != "win32":
        return
    try:
        ps = (
            "Get-CimInstance Win32_Process -Filter \"Name='fceux64.exe'\" | "
            "Where-Object { $_.CommandLine -like '*bridge.lua*' } | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def cleanup_bridge_sessions(prefix: str = "train_") -> None:
    """Удаляет tmp/bridge/<prefix>*/ и зависшие FCEUX bridge-процессы."""
    kill_orphan_fceux_bridge()
    bridge_root = repo_root() / "tmp" / "bridge"
    if not bridge_root.is_dir():
        return
    for stale in (".load_lock", ".reset.lock"):
        stale_path = bridge_root / stale
        if stale_path.is_dir():
            shutil.rmtree(stale_path, ignore_errors=True)
        elif stale_path.is_file():
            try:
                stale_path.unlink()
            except OSError:
                pass
    for entry in bridge_root.iterdir():
        if entry.is_dir() and entry.name.startswith(prefix):
            shutil.rmtree(entry, ignore_errors=True)


def _make_monitored_env(
    *,
    game_id: str,
    mission_id: str,
    rank: int,
    save_state: str,
    reward_profile: str,
    reward_overrides: dict[str, Any] | None,
    turbo: bool,
) -> Monitor:
    from env.loader import make_env

    env = make_env(
        game_id,
        mission_id,
        session_id=f"train_{rank}",
        save_state=save_state,
        turbo=turbo,
        reward_profile=reward_profile,
        reward_overrides=reward_overrides,
    )
    return Monitor(env)


def make_train_env_fn(
    *,
    game_id: str,
    mission_id: str,
    rank: int,
    save_state: str,
    reward_profile: str = "default",
    reward_overrides: dict[str, Any] | None = None,
    turbo: bool = True,
):
    """Callable для SubprocVecEnv / DummyVecEnv."""

    def _init() -> Monitor:
        return _make_monitored_env(
            game_id=game_id,
            mission_id=mission_id,
            rank=rank,
            save_state=save_state,
            reward_profile=reward_profile,
            reward_overrides=reward_overrides,
            turbo=turbo,
        )

    return _init


def build_vec_env(
    *,
    game_id: str,
    mission_id: str,
    n_envs: int,
    save_state: str,
    reward_profile: str = "default",
    reward_overrides: dict[str, Any] | None = None,
    turbo: bool = True,
    subproc: bool = True,
) -> VecEnv:
    """SubprocVecEnv при n_envs>1; DummyVecEnv для отладки."""
    fns = [
        make_train_env_fn(
            game_id=game_id,
            mission_id=mission_id,
            rank=i,
            save_state=save_state,
            reward_profile=reward_profile,
            reward_overrides=reward_overrides,
            turbo=turbo,
        )
        for i in range(n_envs)
    ]
    if n_envs == 1 or not subproc:
        return DummyVecEnv(fns)
    return SubprocVecEnv(fns, start_method="spawn")
