#!/usr/bin/env python3
"""Проигрывание inference FM2 (-playmovie) и playlist.json (один FCEUX на весь плейлист)."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from achievements.airtime import (  # noqa: E402
    DEFAULT_HOLD_FRAMES,
    measure_playlist_airtime,
    overlay_hold_frames,
)
from fceux_launch import fceux_sound_off  # noqa: E402
from fm2_export import (  # noqa: E402
    episode_fm2_guid,
    fm2_has_embedded_savestate,
    read_fm2_guid,
    refresh_fm2_embedded_savestate,
    remap_fm2_guid,
)
from fm2_playback import fceux_playmovie_argv  # noqa: E402
from inference_states import gameplay_start_frame, resolve_inference_reset_state  # noqa: E402
from project_paths import (  # noqa: E402
    count_fm2_frames,
    mission_dir,
    parse_fm2_rom_basename,
    repo_root,
    resolve_fceux_binary,
    resolve_rom,
)
from ram_map_load import load_ram_addresses  # noqa: E402


def _resolve_input_path(path: Path, game: str, mission: str) -> Path:
    if path.is_absolute():
        return path.resolve()
    candidate = mission_dir(game, mission) / path
    return candidate.resolve() if candidate.is_file() else path.resolve()


def _playback_ram_env(game: str, mission: str, env: dict[str, str]) -> None:
    mdir = mission_dir(game, mission)
    try:
        addrs = load_ram_addresses(mdir)
        env["WAIT_PLAYBACK_ROOM"] = str(addrs["room"])
        if "lives" in addrs:
            env["WAIT_PLAYBACK_LIVES"] = str(addrs["lives"])
    except (FileNotFoundError, KeyError):
        pass
    gf = gameplay_start_frame(mdir)
    if gf is not None:
        env["WAIT_PLAYBACK_GAMEPLAY_START"] = str(gf)


def _inference_reset_fc0(game: str, mission: str) -> Path:
    mdir = mission_dir(game, mission)
    return mdir / resolve_inference_reset_state(mdir)


def _stage_rom(rom: Path, staging: Path, rom_base: str) -> Path:
    staged_rom = staging / rom_base
    for name in (rom_base, rom_base + ".nes", rom.name):
        shutil.copy2(rom, staging / name)
    return staged_rom


def _prepare_staged_fm2(
    fm2: Path,
    dest: Path,
    *,
    guid_salt: str,
    game: str,
    mission: str,
) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(fm2, dest)
    clip_guid = episode_fm2_guid(salt=guid_salt)
    remap_fm2_guid(dest, clip_guid)
    refresh_fm2_embedded_savestate(dest, _inference_reset_fc0(game, mission), guid=clip_guid)
    return dest


def _wait_fceux(proc: subprocess.Popen, *, done_flag: Path | None, timeout: float) -> None:
    deadline = time.time() + timeout
    while proc.poll() is None:
        if done_flag is not None and done_flag.is_file():
            time.sleep(0.3)
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
            return
        if time.time() > deadline:
            proc.terminate()
            raise SystemExit(f"FCEUX timeout ({timeout:.0f}s)")
        time.sleep(0.2)
    if proc.returncode not in (0, None):
        raise SystemExit(f"FCEUX exited with code {proc.returncode}")


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

    with fceux_sound_off(fceux.parent):
        proc = subprocess.Popen(cmd, cwd=str(staging), env=env, creationflags=popen_flags)
        _wait_fceux(proc, done_flag=None, timeout=timeout)


def _play_single_fm2(args: argparse.Namespace, fm2: Path) -> None:
    if not fm2_has_embedded_savestate(fm2):
        raise SystemExit(f"FM2 missing embedded savestate: {fm2}")

    sidecar = fm2.with_suffix(".overlay.json")
    overlay_path = Path(args.overlay) if args.overlay else sidecar
    if args.overlay:
        overlay_path = _resolve_input_path(overlay_path, args.game, args.mission)

    rom = resolve_rom(args.game)
    staging = repo_root() / "tmp" / "play_fm2" / "staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    rom_base = parse_fm2_rom_basename(fm2)
    staged_rom = _stage_rom(rom, staging, rom_base)
    staged_fm2 = _prepare_staged_fm2(
        fm2,
        staging / "playback.fm2",
        guid_salt=fm2.stem,
        game=args.game,
        mission=args.mission,
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
    _playback_ram_env(args.game, args.mission, env)

    frames = count_fm2_frames(fm2)
    hold = overlay_hold_frames(overlay_path if overlay_path.is_file() else None)
    timeout = max(args.timeout, (frames + hold) / 60.0 + 20.0)

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
        turbo=args.turbo,
        timeout=timeout,
        noicon=args.noicon,
    )


def _resolve_playlist_clip_fm2(logs_dir: Path, fm2_name: str) -> Path:
    fm2 = Path(fm2_name)
    if not fm2.is_file():
        fm2 = logs_dir / Path(fm2_name).name
    if not fm2.is_file():
        raise SystemExit(f"FM2 not found for playlist clip: {fm2_name}")
    return fm2.resolve()


def _play_playlist(args: argparse.Namespace, playlist_path: Path) -> None:
    """Один FCEUX: Lua movie.play по очереди (achievement_overlay_playlist.lua)."""
    logs_dir = playlist_path.parent
    playlist = json.loads(playlist_path.read_text(encoding="utf-8"))
    clips = playlist.get("clips") or []
    if not clips:
        raise SystemExit(f"Playlist has no clips: {playlist_path}")

    rom = resolve_rom(args.game)
    staging = repo_root() / "tmp" / "play_fm2" / "playlist_staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

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
        staged_fm2 = _prepare_staged_fm2(
            fm2,
            staging / f"{stem}.fm2",
            guid_salt=f"{playlist_path.stem}_{stem}",
            game=args.game,
            mission=args.mission,
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
    staged_rom = _stage_rom(rom, staging, rom_base)
    queue_path.write_text("\n".join(queue_lines) + "\n", encoding="utf-8")

    ram_cfg: dict[str, int] = {}
    mdir = mission_dir(args.game, args.mission)
    try:
        addrs = load_ram_addresses(mdir)
        ram_cfg["room"] = int(addrs["room"])
        if "lives" in addrs:
            ram_cfg["lives"] = int(addrs["lives"])
    except (FileNotFoundError, KeyError, TypeError, ValueError):
        pass

    config = {
        "done_flag": done_flag.name,
        "queue_path": queue_path.name,
        "block_label_frames": 120,
        **ram_cfg,
    }
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    fceux = resolve_fceux_binary()
    lua_src = repo_root() / "fceux" / "lua" / "achievement_overlay_playlist.lua"
    lua_staged = staging / "playlist.lua"
    shutil.copy2(lua_src, lua_staged)
    env = os.environ.copy()
    # Относительный путь: cwd = staging (abs -lua вне staging на win64 не грузится)
    env["WAIT_FCEUX_LUA_CONFIG"] = config_path.name
    _playback_ram_env(args.game, args.mission, env)

    # realtime airtime (fm2 + hold) + запас
    timeout = max(args.timeout, airtime.seconds + 30.0 * len(clips))

    cmd = [str(fceux)]
    if args.noicon:
        cmd.extend(["-noicon", "1"])
    cmd.extend(["-lua", lua_staged.name])
    if args.turbo:
        cmd.extend(["-nothrottle", "1"])
    cmd.append(staged_rom.name)

    popen_flags = 0
    if sys.platform == "win32" and args.noicon:
        popen_flags = subprocess.CREATE_NO_WINDOW

    print(f"Launching one FCEUX for {len(clips)} clip(s), timeout={timeout:.0f}s", flush=True)
    with fceux_sound_off(fceux.parent):
        proc = subprocess.Popen(cmd, cwd=str(staging), env=env, creationflags=popen_flags)
        _wait_fceux(proc, done_flag=done_flag, timeout=timeout)

    if not done_flag.is_file():
        raise SystemExit("Playlist finished without done.flag — check FCEUX/Lua errors")


def main() -> None:
    parser = argparse.ArgumentParser(description="Play inference FM2 (-playmovie) or playlist")
    parser.add_argument("input", help=".fm2 | logs/YYYYMMDD/playlist.json")
    parser.add_argument("--game", default="rushn_attack")
    parser.add_argument("--mission", default="m1")
    parser.add_argument("--overlay", type=Path, default=None)
    parser.add_argument("--turbo", action="store_true", help="ускорить replay")
    parser.add_argument(
        "--noicon",
        action="store_true",
        help="скрытое окно (по умолчанию окно видно для эфира)",
    )
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--skip-preflight", action="store_true")
    args = parser.parse_args()

    if not args.skip_preflight:
        from inference_preflight import require_playback_preflight  # noqa: WPS433

        require_playback_preflight(label="play_inference_fm2")

    input_path = _resolve_input_path(Path(args.input), args.game, args.mission)
    if not input_path.is_file():
        raise SystemExit(f"Input not found: {input_path}")

    if input_path.suffix.lower() == ".fm2":
        _play_single_fm2(args, input_path)
        return

    if input_path.suffix.lower() == ".json" and (
        input_path.name == "playlist.json" or input_path.name.endswith("_playlist.json")
    ):
        _play_playlist(args, input_path)
        return

    raise SystemExit("Expected .fm2 or playlist.json")


if __name__ == "__main__":
    main()
