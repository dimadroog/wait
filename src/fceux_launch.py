"""Запуск FCEUX: профили, subprocess, headless sound-off."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from project_paths import load_yaml, resolve_fceux_binary, repo_root


def load_fceux_profile(name: str = "inference") -> dict:
    """Профиль из fceux/profiles/{name}.yaml."""
    path = repo_root() / "fceux" / "profiles" / f"{name}.yaml"
    if not path.is_file():
        return {}
    return load_yaml(path)


# Windows ShowWindow (hypothesis A — train no-focus)
SW_SHOWMINNOACTIVE = 7


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def fceux_no_focus_enabled(profile_name: str = "train") -> bool:
    """Режим train без перехвата фокуса: env WAIT_FCEUX_NO_FOCUS=1 или profiles/{profile}.yaml."""
    env_val = os.environ.get("WAIT_FCEUX_NO_FOCUS")
    if env_val is not None:
        return _truthy(env_val)
    profile = load_fceux_profile(profile_name)
    return bool(profile.get("no_focus"))


def fceux_obs_format(*, profile_name: str = "train", show_window: bool = False) -> str:
    """obs_format: env WAIT_FCEUX_OBS_FORMAT → inference gd / train profile (default raw)."""
    env_val = os.environ.get("WAIT_FCEUX_OBS_FORMAT")
    if env_val:
        return env_val.strip().lower()
    if show_window:
        return "gd"
    profile = load_fceux_profile(profile_name)
    return str(profile.get("obs_format", "raw")).strip().lower()


def fceux_ipc_transport(*, profile_name: str = "train", show_window: bool = False) -> str:
    """IPC transport: env WAIT_FCEUX_IPC → profile (default v1). v2 — только PoC/benchmark."""
    env_val = os.environ.get("WAIT_FCEUX_IPC")
    if env_val:
        return env_val.strip().lower()
    if show_window:
        profile_name = "inference"
    profile = load_fceux_profile(profile_name)
    return str(profile.get("ipc_transport", "v1")).strip().lower()


def fceux_frame_skip(profile_name: str = "train") -> int:
    profile = load_fceux_profile(profile_name)
    return int(profile.get("frame_skip", 4))


def fceux_no_focus_cmdline() -> list[str]:
    """Hypothesis C: фоновый ввод без фокуса (дополнение к A/B)."""
    return ["-bginput", "1"] if fceux_no_focus_enabled() else []


def win32_popen_kwargs(*, show_window: bool, no_focus: bool) -> dict:
    """Popen kwargs для FCEUX на Windows: minimize-without-activate или legacy CREATE_NO_WINDOW."""
    if sys.platform != "win32":
        return {}
    if show_window:
        return {}
    if no_focus:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = SW_SHOWMINNOACTIVE
        return {"startupinfo": si}
    return {"creationflags": subprocess.CREATE_NO_WINDOW}


@contextmanager
def _fceux_cfg_lock(fceux_dir: Path):
    """Межпроцессная блокировка fceux.cfg (parallel train / record_demos)."""
    lock_path = fceux_dir / ".fceux_cfg.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+", encoding="utf-8") as lockf:
        if sys.platform == "win32":
            import msvcrt

            while True:
                try:
                    lockf.seek(0)
                    msvcrt.locking(lockf.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.05)
        else:
            import fcntl

            fcntl.flock(lockf.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if sys.platform == "win32":
                import msvcrt

                try:
                    lockf.seek(0)
                    msvcrt.locking(lockf.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            else:
                import fcntl

                fcntl.flock(lockf.fileno(), fcntl.LOCK_UN)


def ensure_fceux_sound_off(fceux_dir: Path) -> None:
    """Выключить sound в fceux.cfg (идемпотентно, без restore — безопасно для parallel)."""
    fceux_cfg_path = fceux_dir / "fceux.cfg"
    if not fceux_cfg_path.is_file():
        return
    with _fceux_cfg_lock(fceux_dir):
        original = fceux_cfg_path.read_text(encoding="utf-8", errors="replace")
        if re.search(r'"sound"\s+0\b', original):
            return
        patched = (
            re.sub(r'"sound"\s+\d+', '"sound" 0', original, count=1)
            if '"sound"' in original
            else original.rstrip() + '\n"sound" 0\n'
        )
        fceux_cfg_path.write_text(patched, encoding="utf-8")


@contextmanager
def fceux_sound_off(fceux_dir: Path):
    """Headless: sound=0 в fceux.cfg (parallel-safe, без restore)."""
    ensure_fceux_sound_off(fceux_dir)
    yield


def run_fceux_movie(
    staged_fm2: Path,
    staged_rom: Path,
    lua_script: Path,
    config_path: Path,
    cwd: Path,
    timeout_sec: float,
    done_flag: Path | None = None,
) -> None:
    fceux = resolve_fceux_binary()
    env = os.environ.copy()
    env["WAIT_FCEUX_LUA_CONFIG"] = str(config_path.resolve())

    if done_flag and done_flag.exists():
        done_flag.unlink()

    cmd = [
        str(fceux),
        "-readonly",
        "1",
        "-turbo",
        "1",
        "-nothrottle",
        "1",
        "-noicon",
        "1",
        "-lua",
        str(lua_script.resolve()),
        "-playmovie",
        str(staged_fm2),
        str(staged_rom),
    ]

    with fceux_sound_off(fceux.parent):
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        deadline = time.time() + timeout_sec
        while proc.poll() is None:
            if done_flag and done_flag.is_file():
                proc.wait(timeout=30)
                return
            if time.time() > deadline:
                proc.terminate()
                raise TimeoutError(f"FCEUX timeout ({timeout_sec}s)")
            time.sleep(0.2)
        if proc.returncode not in (0, None):
            raise RuntimeError(f"FCEUX exited with code {proc.returncode}")
