#!/usr/bin/env python3
"""Проигрывание self-contained inference FM2 или playlist.json с achievement overlay."""
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
from project_paths import mission_dir, parse_fm2_rom_basename, repo_root, resolve_fceux_binary, resolve_rom  # noqa: E402
from ram_map_load import load_ram_addresses  # noqa: E402


def _count_fm2_frames(fm2: Path) -> int:
    return sum(1 for line in fm2.read_text(encoding="utf-8", errors="replace").splitlines() if line.startswith("|"))


def _overlay_hold_frames(overlay_path: Path, default: int = 180) -> int:
    if not overlay_path.is_file():
        return default
    try:
        return int(json.loads(overlay_path.read_text(encoding="utf-8")).get("show_until_frame", default))
    except (json.JSONDecodeError, TypeError, ValueError):
        return default


def _require_embedded_fm2(fm2: Path) -> None:
    if not fm2_has_embedded_savestate(fm2):
        raise SystemExit(f"FM2 missing embedded savestate (self-contained required): {fm2}")


def _stage_rom(rom: Path, staging: Path, rom_base: str) -> Path:
    staged_rom = staging / rom_base
    for name in (rom_base, rom_base + ".nes", rom.name):
        shutil.copy2(rom, staging / name)
    return staged_rom


def _resolve_input_path(path: Path, game: str, mission: str) -> Path:
    if path.is_absolute():
        return path.resolve()
    candidate = mission_dir(game, mission) / path
    return candidate.resolve() if candidate.is_file() else path.resolve()


def _inference_reset_fc0(game: str, mission: str) -> Path:
    mdir = mission_dir(game, mission)
    rel = resolve_inference_reset_state(mdir)
    return mdir / rel


def _stage_clip(
    fm2: Path,
    rom: Path,
    overlay_path: Path | None,
    staging: Path,
    *,
    guid_salt: str,
    game: str,
    mission: str,
) -> tuple[Path, Path, Path | None]:
    staging.mkdir(parents=True, exist_ok=True)
    staged_fm2 = staging / "playback.fm2"
    shutil.copy2(fm2, staged_fm2)
    clip_guid = episode_fm2_guid(salt=guid_salt)
    remap_fm2_guid(staged_fm2, clip_guid)
    inference_fc0 = _inference_reset_fc0(game, mission)
    refresh_fm2_embedded_savestate(staged_fm2, inference_fc0, guid=clip_guid)
    rom_base = parse_fm2_rom_basename(fm2)
    staged_rom = _stage_rom(rom, staging, rom_base)
    staged_overlay: Path | None = None
    if overlay_path and overlay_path.is_file():
        staged_overlay = staging / overlay_path.name
        shutil.copy2(overlay_path, staged_overlay)
    return staged_fm2, staged_rom, staged_overlay


def _playback_ram_env(game: str, mission: str, env: dict[str, str]) -> None:
    """RAM-адреса для диагностического HUD в achievement_overlay.lua."""
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


def _run_fceux_clip(
    *,
    fceux: Path,
    lua: Path,
    staging: Path,
    staged_fm2: Path,
    staged_rom: Path,
    env: dict[str, str],
    turbo: bool,
    timeout: float,
) -> None:
    cmd = [
        str(fceux),
        "-noicon",
        "1",
        "-lua",
        str(lua.resolve()),
    ]
    if turbo:
        cmd.extend(["-nothrottle", "1"])
    cmd.extend(fceux_playmovie_argv(staged_fm2=staged_fm2, staged_rom=staged_rom))

    with fceux_sound_off(fceux.parent):
        proc = subprocess.Popen(cmd, cwd=str(staging), env=env)
        deadline = time.time() + timeout
        while proc.poll() is None:
            if time.time() > deadline:
                proc.terminate()
                raise SystemExit(f"FCEUX timeout ({timeout:.0f}s)")
            time.sleep(0.2)
        if proc.returncode not in (0, None):
            raise SystemExit(f"FCEUX exited with code {proc.returncode}")


def _play_single_fm2(args: argparse.Namespace, fm2: Path) -> None:
    _require_embedded_fm2(fm2)
    sidecar = fm2.with_suffix(".overlay.json")
    overlay_path = Path(args.overlay) if args.overlay else sidecar

    rom = resolve_rom(args.game)
    staging = repo_root() / "tmp" / "play_fm2" / "staging"
    staged_fm2, staged_rom, staged_overlay = _stage_clip(
        fm2,
        rom,
        overlay_path if overlay_path.is_file() else None,
        staging,
        guid_salt=fm2.stem,
        game=args.game,
        mission=args.mission,
    )

    portable_movies = repo_root() / "fceux" / "portable" / "movies"
    rom_base = parse_fm2_rom_basename(fm2)
    for stray in sorted(portable_movies.glob("*.fm2")):
        if parse_fm2_rom_basename(stray) != rom_base:
            continue
        print(
            f"Warning: {stray} shares romFilename with inference clip; "
            "FCEUX may substitute wrong movie — remove from fceux/portable/movies/",
            file=sys.stderr,
        )
        break

    fceux = resolve_fceux_binary()
    lua = repo_root() / "fceux" / "lua" / "achievement_overlay.lua"
    env = os.environ.copy()
    if staged_overlay and staged_overlay.is_file():
        env["WAIT_ACHIEVEMENT_OVERLAY"] = str(staged_overlay.resolve())
    elif overlay_path.is_file():
        env["WAIT_ACHIEVEMENT_OVERLAY"] = str(overlay_path.resolve())
    else:
        print(f"Warning: overlay not found: {overlay_path}", file=sys.stderr)
    _playback_ram_env(args.game, args.mission, env)

    frames = _count_fm2_frames(fm2)
    overlay_hold = _overlay_hold_frames(overlay_path if overlay_path.is_file() else sidecar)
    timeout = max(args.timeout, (frames + overlay_hold) / 30.0 + 10.0)

    print(
        f"Playing {fm2.name} ({frames} frames), "
        f"embed=refreshed guid={read_fm2_guid(staged_fm2)}",
        flush=True,
    )
    if overlay_path.is_file():
        print(f"Overlay: {overlay_path}")

    _run_fceux_clip(
        fceux=fceux,
        lua=lua,
        staging=staging,
        staged_fm2=staged_fm2,
        staged_rom=staged_rom,
        env=env,
        turbo=args.turbo,
        timeout=timeout,
    )


def _play_playlist(args: argparse.Namespace, playlist_path: Path) -> None:
    logs_dir = playlist_path.parent
    playlist = json.loads(playlist_path.read_text(encoding="utf-8"))
    clips = playlist.get("clips") or []
    if not clips:
        raise SystemExit(f"Playlist has no clips: {playlist_path}")

    rom = resolve_rom(args.game)
    staging_root = repo_root() / "tmp" / "play_fm2" / "staging"
    fceux = resolve_fceux_binary()
    lua = repo_root() / "fceux" / "lua" / "achievement_overlay.lua"
    total_timeout = 0.0

    for clip in clips:
        fm2 = logs_dir / clip["fm2"]
        if not fm2.is_file():
            raise SystemExit(f"FM2 not found for playlist: {fm2}")
        _require_embedded_fm2(fm2)
        overlay_name = clip.get("overlay") or fm2.with_suffix(".overlay.json").name
        overlay_path = logs_dir / overlay_name
        frames = _count_fm2_frames(fm2)
        hold = _overlay_hold_frames(overlay_path)
        total_timeout += (frames + hold) / 30.0 + 5.0

    timeout = max(args.timeout, total_timeout + 10.0)
    print(
        f"Playlist {playlist_path.name}: {len(clips)} clip(s), "
        f"timeout ~{total_timeout:.0f}s",
        flush=True,
    )

    for clip_idx, clip in enumerate(clips, start=1):
        fm2 = logs_dir / clip["fm2"]
        overlay_name = clip.get("overlay") or fm2.with_suffix(".overlay.json").name
        overlay_path = logs_dir / overlay_name

        if staging_root.exists():
            shutil.rmtree(staging_root)
        staging_root.mkdir(parents=True)
        staged_fm2, staged_rom, staged_overlay = _stage_clip(
            fm2,
            rom,
            overlay_path if overlay_path.is_file() else None,
            staging_root,
            guid_salt=fm2.stem,
            game=args.game,
            mission=args.mission,
        )

        env = os.environ.copy()
        if staged_overlay and staged_overlay.is_file():
            env["WAIT_ACHIEVEMENT_OVERLAY"] = str(staged_overlay.resolve())
        elif overlay_path.is_file():
            env["WAIT_ACHIEVEMENT_OVERLAY"] = str(overlay_path.resolve())
        if clip.get("block_label"):
            env["WAIT_BLOCK_LABEL"] = str(clip["block_label"])
        _playback_ram_env(args.game, args.mission, env)

        frames = _count_fm2_frames(staged_fm2)
        hold = _overlay_hold_frames(overlay_path if overlay_path.is_file() else staged_overlay)
        clip_timeout = max(30.0, (frames + hold) / 30.0 + 10.0)

        print(
            f"  clip {clip_idx}/{len(clips)}: {clip['fm2']} "
            f"({clip.get('block_label', '')})",
            flush=True,
        )
        _run_fceux_clip(
            fceux=fceux,
            lua=lua,
            staging=staging_root,
            staged_fm2=staged_fm2,
            staged_rom=staged_rom,
            env=env,
            turbo=args.turbo,
            timeout=min(clip_timeout, timeout),
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Play self-contained inference FM2 or playlist.json")
    parser.add_argument(
        "input",
        help="путь к .fm2 или .playlist.json (напр. logs/20260705_playlist.json)",
    )
    parser.add_argument("--game", default="rushn_attack")
    parser.add_argument("--mission", default="m1")
    parser.add_argument("--overlay", default=None, help="путь к .overlay.json (single FM2)")
    parser.add_argument("--turbo", action="store_true", help="макс. скорость (без throttle)")
    parser.add_argument("--timeout", type=float, default=120.0, help="минимальный timeout (сек)")
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="не вызывать playback preflight (inference_local.sh чистит отдельно)",
    )
    args = parser.parse_args()

    if not args.skip_preflight:
        from inference_preflight import require_playback_preflight  # noqa: WPS433

        require_playback_preflight(label="play_inference_fm2")

    input_path = _resolve_input_path(Path(args.input), args.game, args.mission)
    if not input_path.is_file():
        raise SystemExit(f"Input not found: {input_path}")

    if input_path.suffix.lower() == ".json" and input_path.name.endswith("_playlist.json"):
        _play_playlist(args, input_path)
    elif input_path.suffix.lower() == ".fm2":
        _play_single_fm2(args, input_path)
    else:
        raise SystemExit("Expected .fm2 or YYYYMMDD_playlist.json")


if __name__ == "__main__":
    main()
