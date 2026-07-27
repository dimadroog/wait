"""Операторский проигрыш FM2 / playlist (эфир и GUI-отладка)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from contextlib import nullcontext
from pathlib import Path

from achievements.airtime import (
    DEFAULT_HOLD_FRAMES,
    measure_playlist_airtime,
    overlay_hold_frames,
)
from fceux_launch import apply_operator_fceux_cfg, ensure_fceux_sound_on, fceux_sound_off
from fm2_export import fm2_has_embedded_savestate, read_fm2_guid
from fm2_playback import (
    fceux_playmovie_argv,
    inference_reset_fc0,
    prepare_playback_fm2,
    reset_staging_dir,
    resolve_mission_relative_path,
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


def _run_fceux_movie_clip(
    *,
    fceux: Path,
    lua: Path,
    staging: Path,
    staged_fm2: Path,
    staged_rom: Path,
    env: dict[str, str],
    turbo: bool,
    timeout: float,
    noicon: bool,
) -> None:
    cmd = [str(fceux)]
    if noicon:
        cmd.extend(["-noicon", "1"])
    cmd.extend(["-lua", Path(lua).name])
    if turbo:
        cmd.extend(["-nothrottle", "1"])
    cmd.extend(fceux_playmovie_argv(staged_fm2=staged_fm2, staged_rom=staged_rom))

    popen_flags = 0
    if sys.platform == "win32" and noicon:
        popen_flags = subprocess.CREATE_NO_WINDOW

    if noicon:
        sound_ctx = fceux_sound_off(fceux.parent)
    else:
        apply_operator_fceux_cfg(fceux.parent)
        sound_ctx = nullcontext()
    with sound_ctx:
        proc = subprocess.Popen(cmd, cwd=str(staging), env=env, creationflags=popen_flags)
        try:
            wait_fceux_process(proc, done_flag=None, timeout=timeout)
        except TimeoutError as e:
            raise SystemExit(str(e)) from e
        except RuntimeError as e:
            raise SystemExit(str(e)) from e


def play_single_fm2(
    fm2: Path,
    *,
    game: str,
    mission: str,
    overlay: Path | None = None,
    turbo: bool = False,
    noicon: bool = False,
    timeout: float = 120.0,
) -> None:
    """Один FM2 через achievement_overlay_movie.lua (-playmovie)."""
    if not fm2_has_embedded_savestate(fm2):
        raise SystemExit(f"FM2 missing embedded savestate: {fm2}")

    sidecar = fm2.with_suffix(".overlay.json")
    overlay_path = overlay if overlay is not None else sidecar
    if overlay is not None:
        overlay_path = resolve_mission_relative_path(overlay_path, game, mission)

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
    if overlay_path.is_file():
        shutil.copy2(overlay_path, staging / overlay_path.name)
        staged_overlay = staging / overlay_path.name
    else:
        staged_overlay = None

    fceux = resolve_fceux_binary()
    lua_src = repo_root() / "fceux" / "lua" / "achievement_overlay_movie.lua"
    lua_staged = staging / "overlay_movie.lua"
    shutil.copy2(lua_src, lua_staged)
    env = os.environ.copy()
    if staged_overlay is not None:
        env["WAIT_ACHIEVEMENT_OVERLAY"] = staged_overlay.name
    elif overlay_path.is_file():
        env["WAIT_ACHIEVEMENT_OVERLAY"] = str(overlay_path.resolve())
    else:
        print(f"Warning: overlay not found: {overlay_path}", file=sys.stderr)

    frames = count_fm2_frames(fm2)
    hold = overlay_hold_frames(overlay_path if overlay_path.is_file() else None)
    timeout_sec = max(timeout, (frames + hold) / 60.0 + 20.0)

    print(
        f"Playing FM2 {fm2.name} ({frames} frames), "
        f"embed=refreshed guid={read_fm2_guid(staged_fm2)}",
        flush=True,
    )
    if overlay_path.is_file():
        print(f"Overlay: {overlay_path}")

    _run_fceux_movie_clip(
        fceux=fceux,
        lua=lua_staged,
        staging=staging,
        staged_fm2=staged_fm2,
        staged_rom=staged_rom,
        env=env,
        turbo=turbo,
        timeout=timeout_sec,
        noicon=noicon,
    )


def _resolve_playlist_clip_fm2(logs_dir: Path, fm2_name: str) -> Path:
    fm2 = Path(fm2_name)
    if not fm2.is_file():
        fm2 = logs_dir / Path(fm2_name).name
    if not fm2.is_file():
        raise SystemExit(f"FM2 not found for playlist clip: {fm2_name}")
    return fm2.resolve()


def play_playlist(
    playlist_path: Path,
    *,
    game: str,
    mission: str,
    turbo: bool = False,
    noicon: bool = False,
    timeout: float = 120.0,
) -> None:
    """Один FCEUX: Lua movie.play по очереди (achievement_overlay_playlist.lua)."""
    logs_dir = playlist_path.parent
    playlist = json.loads(playlist_path.read_text(encoding="utf-8"))
    clips = playlist.get("clips") or []
    if not clips:
        raise SystemExit(f"Playlist has no clips: {playlist_path}")

    rom = resolve_rom(game)
    staging = reset_staging_dir(repo_root() / "tmp" / "play_fm2" / "playlist_staging")

    queue_path = staging / "queue.jsonl"
    done_flag = staging / "done.flag"
    config_path = staging / "config.json"
    if done_flag.exists():
        done_flag.unlink()

    airtime = measure_playlist_airtime(playlist_path)
    hold_by_fm2 = {c.fm2: c.hold_frames for c in airtime.clips}
    queue_lines: list[str] = []
    rom_base: str | None = None

    print(
        f"Playlist {playlist_path.name}: {len(clips)} clip(s) -> one FCEUX "
        f"(airtime~{airtime.seconds:.1f}s / {airtime.hours:.3f}h)",
        flush=True,
    )
    for clip_idx, clip in enumerate(clips, start=1):
        fm2_name = clip.get("fm2") or clip.get("fm2_path")
        if not fm2_name:
            raise SystemExit(f"Clip missing fm2: {clip}")
        fm2 = _resolve_playlist_clip_fm2(logs_dir, str(fm2_name))
        if not fm2_has_embedded_savestate(fm2):
            raise SystemExit(f"FM2 missing embedded savestate: {fm2}")
        if rom_base is None:
            rom_base = parse_fm2_rom_basename(fm2)

        stem = f"clip_{clip_idx:03d}"
        staged_fm2 = prepare_playback_fm2(
            fm2,
            staging / f"{stem}.fm2",
            guid_salt=f"{playlist_path.stem}_{stem}",
            game=game,
            mission=mission,
        )
        overlay_name = clip.get("overlay")
        overlay_src = logs_dir / overlay_name if overlay_name else fm2.with_suffix(".overlay.json")
        staged_overlay_name = ""
        hold = hold_by_fm2.get(fm2.name, DEFAULT_HOLD_FRAMES)
        if overlay_src.is_file():
            staged_overlay = staging / f"{stem}.overlay.json"
            shutil.copy2(overlay_src, staged_overlay)
            staged_overlay_name = staged_overlay.name
            hold = overlay_hold_frames(staged_overlay)

        block_label = str(clip.get("block_label") or "")
        queue_lines.append(
            json.dumps(
                {
                    "fm2": staged_fm2.name,
                    "overlay": staged_overlay_name,
                    "block_label": block_label,
                    "hold": hold,
                },
                ensure_ascii=False,
            )
        )
        frames = count_fm2_frames(fm2)
        print(
            f"  clip {clip_idx}/{len(clips)}: {fm2.name} ({frames} frames, {block_label})",
            flush=True,
        )

    assert rom_base is not None
    staged_rom = stage_rom(rom, staging, rom_base)
    queue_path.write_text("\n".join(queue_lines) + "\n", encoding="utf-8")

    config = {
        "done_flag": done_flag.name,
        "queue_path": queue_path.name,
        "block_label_frames": 120,
    }
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    fceux = resolve_fceux_binary()
    lua_src = repo_root() / "fceux" / "lua" / "achievement_overlay_playlist.lua"
    lua_staged = staging / "playlist.lua"
    shutil.copy2(lua_src, lua_staged)
    env = os.environ.copy()
    env["WAIT_FCEUX_LUA_CONFIG"] = config_path.name

    timeout_sec = max(timeout, airtime.seconds + 30.0 * len(clips))

    cmd = [str(fceux)]
    if noicon:
        cmd.extend(["-noicon", "1"])
    cmd.extend(["-lua", lua_staged.name])
    if turbo:
        cmd.extend(["-nothrottle", "1"])
    cmd.append(staged_rom.name)

    popen_flags = 0
    if sys.platform == "win32" and noicon:
        popen_flags = subprocess.CREATE_NO_WINDOW

    print(f"Launching one FCEUX for {len(clips)} clip(s), timeout={timeout_sec:.0f}s", flush=True)
    if noicon:
        sound_ctx = fceux_sound_off(fceux.parent)
    else:
        apply_operator_fceux_cfg(fceux.parent)
        sound_ctx = nullcontext()
    with sound_ctx:
        proc = subprocess.Popen(cmd, cwd=str(staging), env=env, creationflags=popen_flags)
        try:
            wait_fceux_process(proc, done_flag=done_flag, timeout=timeout_sec)
        except TimeoutError as e:
            raise SystemExit(str(e)) from e
        except RuntimeError as e:
            raise SystemExit(str(e)) from e

    if not done_flag.is_file():
        raise SystemExit("Playlist finished without done.flag — check FCEUX/Lua errors")


def play_gui_fm2(
    fm2: Path,
    *,
    game: str,
    mission: str,
    refresh_embed: bool = True,
    turbo: bool = False,
    timeout: float = 0.0,
) -> None:
    """Визуальный просмотр self-contained FM2 в окне FCEUX (без overlay Lua)."""
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
    overlay: Path | None = None,
    turbo: bool = False,
    noicon: bool = False,
    timeout: float = 120.0,
) -> None:
    """Диспетчер: .fm2 → play_single_fm2; playlist.json → play_playlist."""
    if input_path.suffix.lower() == ".fm2":
        play_single_fm2(
            input_path,
            game=game,
            mission=mission,
            overlay=overlay,
            turbo=turbo,
            noicon=noicon,
            timeout=timeout,
        )
        return

    if input_path.suffix.lower() == ".json" and (
        input_path.name == "playlist.json" or input_path.name.endswith("_playlist.json")
    ):
        play_playlist(
            input_path,
            game=game,
            mission=mission,
            turbo=turbo,
            noicon=noicon,
            timeout=timeout,
        )
        return

    raise SystemExit("Expected .fm2 or playlist.json")
