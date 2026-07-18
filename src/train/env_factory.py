"""Фабрика vec-env для SubprocVecEnv (pickle-safe на Windows)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv, VecEnv

from project_paths import repo_root

DEFAULT_BRIDGE_PREFIXES = ("train_", "bench_")

TRAIN_ORPHAN_SCRIPT_MARKERS = (
    "benchmark_train.py",
    "train_ppo.py",
    "stress_e2e_gate.py",
    "test_parallel_env.py",
    "benchmark_bridge.py",
    "bench_parallel_step.py",
)

_WIN32_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _bridge_tmp_path_literals() -> tuple[str, str]:
    bridge_root = (repo_root() / "tmp" / "bridge").resolve()
    return bridge_root.as_posix(), str(bridge_root)


def _win32_run_ps(script: str) -> str:
    if sys.platform != "win32":
        return ""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=_WIN32_CREATE_NO_WINDOW,
        )
        if result.returncode != 0:
            return ""
        return (result.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _ps_fceux_orphan_where() -> str:
    posix, win = _bridge_tmp_path_literals()
    posix = posix.replace("'", "''")
    win = win.replace("'", "''")
    return (
        "$cl = $_.CommandLine; "
        f"($cl -like '*bridge.lua*' -or $cl -like '*{posix}*' -or $cl -like '*{win}*')"
    )


def _ps_train_python_orphan_where(*, exclude_pid: int) -> str:
    markers = ", ".join(f"'{m}'" for m in TRAIN_ORPHAN_SCRIPT_MARKERS)
    return (
        f"$me = {exclude_pid}; "
        f"$markers = @({markers}); "
        "$_.ProcessId -ne $me -and ($_.Name -like 'python*.exe') -and "
        "($markers | Where-Object { $_.CommandLine -like ('*' + $_ + '*') }).Count -gt 0"
    )


def count_orphan_fceux_bridge() -> int:
    """Число orphan fceux64.exe (bridge.lua или tmp/bridge session)."""
    if sys.platform != "win32":
        return 0
    script = (
        f"$n = @(Get-CimInstance Win32_Process -Filter \"Name='fceux64.exe'\" | "
        f"Where-Object {{ {_ps_fceux_orphan_where()} }}).Count; "
        "Write-Output $n"
    )
    try:
        return int(_win32_run_ps(script) or "0")
    except ValueError:
        return 0


def count_orphan_train_python() -> int:
    """Число зависших python gate/train/benchmark (не текущий процесс)."""
    if sys.platform != "win32":
        return 0
    script = (
        "$n = @(Get-CimInstance Win32_Process | "
        f"Where-Object {{ {_ps_train_python_orphan_where(exclude_pid=os.getpid())} }}).Count; "
        "Write-Output $n"
    )
    try:
        return int(_win32_run_ps(script) or "0")
    except ValueError:
        return 0


@dataclass(frozen=True)
class PreflightResult:
    orphans_before: int
    fceux_before: int
    python_before: int
    fceux_after: int
    python_after: int
    prefixes: tuple[str, ...]


def _run_preflight_cleanup(
    *,
    prefixes: tuple[str, ...] = DEFAULT_BRIDGE_PREFIXES,
) -> PreflightResult:
    fceux_before = count_orphan_fceux_bridge()
    python_before = count_orphan_train_python()
    for prefix in prefixes:
        cleanup_bridge_sessions(prefix)
    fceux_after = count_orphan_fceux_bridge()
    python_after = count_orphan_train_python()
    return PreflightResult(
        orphans_before=fceux_before + python_before,
        fceux_before=fceux_before,
        python_before=python_before,
        fceux_after=fceux_after,
        python_after=python_after,
        prefixes=prefixes,
    )


def _print_preflight_messages(result: PreflightResult, *, label: str) -> None:
    if result.fceux_before > 0:
        print(
            f"WARNING [{label}]: {result.fceux_before} orphan fceux64.exe "
            f"(bridge.lua / tmp/bridge) before cleanup"
        )
    if result.python_before > 0:
        print(
            f"WARNING [{label}]: {result.python_before} orphan python "
            f"(train/benchmark scripts) before cleanup"
        )
    if result.fceux_after > 0:
        print(
            f"WARNING [{label}]: {result.fceux_after} fceux64.exe still running after cleanup"
        )
    if result.python_after > 0:
        print(
            f"WARNING [{label}]: {result.python_after} python still running after cleanup"
        )
    if result.orphans_before > 0 and result.fceux_after == 0 and result.python_after == 0:
        print(
            f"preflight [{label}]: orphans cleared "
            f"(fceux={result.fceux_before}, python={result.python_before})"
        )
    elif result.orphans_before == 0:
        prefix_list = ", ".join(result.prefixes)
        print(f"preflight [{label}]: no orphan processes ({prefix_list} IPC cleared)")


def preflight_bridge_sessions(
    *,
    label: str = "preflight",
    prefixes: tuple[str, ...] = DEFAULT_BRIDGE_PREFIXES,
) -> int:
    """Перед gate/stress: cleanup IPC + orphan FCEUX/python; предупреждение при orphan > 0."""
    result = _run_preflight_cleanup(prefixes=prefixes)
    _print_preflight_messages(result, label=label)
    return result.orphans_before


def require_clean_preflight(
    *,
    label: str = "preflight",
    prefixes: tuple[str, ...] = DEFAULT_BRIDGE_PREFIXES,
) -> None:
    """Обязательная очистка перед train: abort, если после cleanup остались orphan-процессы."""
    result = _run_preflight_cleanup(prefixes=prefixes)
    _print_preflight_messages(result, label=label)
    if result.fceux_after > 0 or result.python_after > 0:
        raise SystemExit(
            f"preflight [{label}] failed: fceux={result.fceux_after} "
            f"python={result.python_after} still running after cleanup. "
            "Stop orphan processes manually (Windows: taskkill /F /IM fceux64.exe), then retry."
        )


def kill_orphan_fceux_bridge() -> None:
    """Завершить orphan FCEUX (bridge.lua / tmp/bridge) и зависшие python train/benchmark."""
    if sys.platform != "win32":
        return
    pid = os.getpid()
    fceux_ps = (
        "Get-CimInstance Win32_Process -Filter \"Name='fceux64.exe'\" | "
        f"Where-Object {{ {_ps_fceux_orphan_where()} }} | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    python_ps = (
        "Get-CimInstance Win32_Process | "
        f"Where-Object {{ {_ps_train_python_orphan_where(exclude_pid=pid)} }} | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    _win32_run_ps(fceux_ps)
    _win32_run_ps(python_ps)


def cleanup_bridge_sessions(prefix: str = "train_") -> None:
    """Удаляет tmp/bridge/<prefix>*/ и зависшие FCEUX / train python."""
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
    death_mode: str | None = None,
) -> Monitor:
    from env.loader import make_env

    kwargs: dict[str, Any] = {
        "session_id": f"train_{rank}",
        "save_state": save_state,
        "turbo": turbo,
        "reward_profile": reward_profile,
        "reward_overrides": reward_overrides,
    }
    if death_mode:
        kwargs["death_mode"] = death_mode
    env = make_env(game_id, mission_id, **kwargs)
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
    death_mode: str | None = None,
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
            death_mode=death_mode,
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
    death_mode: str | None = None,
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
            death_mode=death_mode,
        )
        for i in range(n_envs)
    ]
    if n_envs == 1 or not subproc:
        return DummyVecEnv(fns)
    return SubprocVecEnv(fns, start_method="spawn")
