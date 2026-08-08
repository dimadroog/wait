"""Операторский проигрыш одного FM2 (GUI-отладка / просмотр клипа)."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from contextlib import nullcontext
from pathlib import Path

from fceux_launch import apply_operator_fceux_cfg, ensure_fceux_sound_on, fceux_sound_off
from fm2_export import fm2_has_embedded_savestate, read_fm2_guid
from fm2_playback import (
    fceux_playmovie_argv,
    inference_reset_fc0,
    prepare_playback_fm2,
    reset_staging_dir,
    stage_rom,
    wait_fceux_process,
)
from project_paths import (
    count_fm2_frames,
    parse_fm2_rom_basename,
    repo_root,
    resolve_fceux_binary,
    resolve_rom,
)


def play_single_fm2(
    fm2: Path,
    *,
    game: str,
    mission: str,
    turbo: bool = False,
    noicon: bool = False,
    timeout: float = 120.0,
) -> None:
    """Один self-contained FM2 через FCEUX -playmovie (без overlay HUD)."""
    if not fm2_has_embedded_savestate(fm2):
        raise SystemExit(f"FM2 missing embedded savestate: {fm2}")

    rom = resolve_rom(game)
    staging = reset_staging_dir(repo_root() / "tmp" / "play_fm2" / "staging")
    rom_base = parse_fm2_rom_basename(fm2)
    staged_rom = stage_rom(rom, staging, rom_base)
    staged_fm2 = prepare_playback_fm2(
        fm2,
        staging / "playback.fm2",
        guid_salt=fm2.stem,
        game=game,
        mission=mission,
    )

    fceux = resolve_fceux_binary()
    frames = count_fm2_frames(fm2)
    timeout_sec = max(timeout, frames / 60.0 + 20.0)

    print(
        f"Playing FM2 {fm2.name} ({frames} frames), "
        f"embed=refreshed guid={read_fm2_guid(staged_fm2)}",
        flush=True,
    )

    cmd = [str(fceux)]
    if noicon:
        cmd.extend(["-noicon", "1"])
    if turbo:
        cmd.extend(["-nothrottle", "1"])
    cmd.extend(fceux_playmovie_argv(staged_fm2=staged_fm2, staged_rom=staged_rom))

    popen_flags = 0
    if sys.platform == "win32" and noicon:
        popen_flags = subprocess.CREATE_NO_WINDOW

    env = os.environ.copy()
    if noicon:
        sound_ctx = fceux_sound_off(fceux.parent)
    else:
        apply_operator_fceux_cfg(fceux.parent)
        sound_ctx = nullcontext()
    with sound_ctx:
        proc = subprocess.Popen(cmd, cwd=str(staging), env=env, creationflags=popen_flags)
        try:
            wait_fceux_process(proc, done_flag=None, timeout=timeout_sec)
        except TimeoutError as e:
            raise SystemExit(str(e)) from e
        except RuntimeError as e:
            raise SystemExit(str(e)) from e


def play_gui_fm2(
    fm2: Path,
    *,
    game: str,
    mission: str,
    refresh_embed: bool = True,
    turbo: bool = False,
    timeout: float = 0.0,
) -> None:
    """Визуальный просмотр self-contained FM2 в окне FCEUX."""
    if fm2.suffix.lower() != ".fm2":
        raise SystemExit(f"Not an FM2 file: {fm2}")
    if not refresh_embed and not fm2_has_embedded_savestate(fm2):
        raise SystemExit(f"FM2 has no embedded savestate: {fm2}")

    rom = resolve_rom(game)
    staging = reset_staging_dir(repo_root() / "tmp" / "play_fm2_gui" / "staging")

    staged_fm2 = prepare_playback_fm2(
        fm2,
        staging / fm2.name,
        guid_salt=f"gui-{fm2.stem}",
        game=game,
        mission=mission,
        refresh_embed=refresh_embed,
    )
    if refresh_embed:
        print(f"Refreshed embed from {inference_reset_fc0(game, mission).name}")

    rom_base = parse_fm2_rom_basename(staged_fm2)
    stage_rom(rom, staging, rom_base)

    frames = count_fm2_frames(staged_fm2)
    timeout_sec = timeout if timeout > 0 else frames / 60.0 + 30.0

    fceux = resolve_fceux_binary()
    cmd = [str(fceux)]
    if turbo:
        cmd.extend(["-turbo", "1", "-nothrottle", "1"])
    cmd.extend(fceux_playmovie_argv(staged_fm2=staged_fm2, staged_rom=staging / rom_base))

    print(f"Playing {fm2.name} ({frames} frames) — смотрите окно FCEUX", flush=True)
    print(f"  cwd={staging}")
    print(f"  expect: gameplay (мост) с первых кадров, не title «1 PLAYER»", flush=True)

    env = os.environ.copy()
    ensure_fceux_sound_on(fceux.parent)
    proc = subprocess.Popen(cmd, cwd=str(staging), env=env)
    try:
        proc.wait(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)
        print(f"Stopped after {timeout_sec:.0f}s (movie may still be playing)", flush=True)
    else:
        print(f"FCEUX exit code {proc.returncode}", flush=True)

    time.sleep(0.2)


def play_input(
    input_path: Path,
    *,
    game: str,
    mission: str,
    turbo: bool = False,
    noicon: bool = False,
    timeout: float = 120.0,
) -> None:
    """Проигрыш одного .fm2."""
    if input_path.suffix.lower() == ".fm2":
        play_single_fm2(
            input_path,
            game=game,
            mission=mission,
            turbo=turbo,
            noicon=noicon,
            timeout=timeout,
        )
        return

    raise SystemExit("Expected .fm2")
