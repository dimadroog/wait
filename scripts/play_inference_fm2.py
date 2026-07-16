#!/usr/bin/env python3
"""Проигрывание inference: .fm2 (-playmovie) или playlist/jsonl (фаза C2 / legacy 3.4)."""
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
from inference_replay import replay_frame_count, run_inference_playback  # noqa: E402
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


def _overlay_hold_frames(overlay_path: Path | None, default: int = 180) -> int:
    if not overlay_path or not overlay_path.is_file():
        return default
    try:
        return int(json.loads(overlay_path.read_text(encoding="utf-8")).get("show_until_frame", default))
    except (json.JSONDecodeError, TypeError, ValueError):
        return default


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


def _stage_fm2_clip(
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
    refresh_fm2_embedded_savestate(staged_fm2, _inference_reset_fc0(game, mission), guid=clip_guid)
    rom_base = parse_fm2_rom_basename(fm2)
    staged_rom = _stage_rom(rom, staging, rom_base)
    staged_overlay: Path | None = None
    if overlay_path and overlay_path.is_file():
        staged_overlay = staging / overlay_path.name
        shutil.copy2(overlay_path, staged_overlay)
    return staged_fm2, staged_rom, staged_overlay


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
    cmd.extend(["-lua", str(lua.resolve())])
    if turbo:
        cmd.extend(["-nothrottle", "1"])
    cmd.extend(fceux_playmovie_argv(staged_fm2=staged_fm2, staged_rom=staged_rom))

    popen_flags = 0
    if sys.platform == "win32" and noicon:
        popen_flags = subprocess.CREATE_NO_WINDOW

    with fceux_sound_off(fceux.parent):
        proc = subprocess.Popen(cmd, cwd=str(staging), env=env, creationflags=popen_flags)
        deadline = time.time() + timeout
        while proc.poll() is None:
            if time.time() > deadline:
                proc.terminate()
                raise SystemExit(f"FCEUX timeout ({timeout:.0f}s)")
            time.sleep(0.2)
        if proc.returncode not in (0, None):
            raise SystemExit(f"FCEUX exited with code {proc.returncode}")


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
    staged_fm2, staged_rom, staged_overlay = _stage_fm2_clip(
        fm2,
        rom,
        overlay_path if overlay_path.is_file() else None,
        staging,
        guid_salt=fm2.stem,
        game=args.game,
        mission=args.mission,
    )

    fceux = resolve_fceux_binary()
    lua = repo_root() / "fceux" / "lua" / "achievement_overlay_movie.lua"
    env = os.environ.copy()
    if staged_overlay and staged_overlay.is_file():
        env["WAIT_ACHIEVEMENT_OVERLAY"] = str(staged_overlay.resolve())
    elif overlay_path.is_file():
        env["WAIT_ACHIEVEMENT_OVERLAY"] = str(overlay_path.resolve())
    else:
        print(f"Warning: overlay not found: {overlay_path}", file=sys.stderr)
    _playback_ram_env(args.game, args.mission, env)

    frames = count_fm2_frames(fm2)
    hold = _overlay_hold_frames(overlay_path if overlay_path.is_file() else None)
    timeout = max(args.timeout, (frames + hold) / 60.0 + 20.0)

    print(
        f"Playing FM2 {fm2.name} ({frames} frames), "
        f"embed=refreshed guid={read_fm2_guid(staged_fm2)}",
        flush=True,
    )
    if overlay_path.is_file():
        print(f"Overlay: {overlay_path}")
    print("Expect: gameplay (мост) + overlay HUD — не title «1 PLAYER»", flush=True)

    _run_fceux_movie_clip(
        fceux=fceux,
        lua=lua,
        staging=staging,
        staged_fm2=staged_fm2,
        staged_rom=staged_rom,
        env=env,
        turbo=args.turbo,
        timeout=timeout,
        noicon=args.noicon,
    )


def _play_episode_jsonl(
    args: argparse.Namespace,
    *,
    jsonl_path: Path,
    episode: int,
    overlay_path: Path | None,
    block_label: str | None = None,
) -> None:
    """Legacy 3.4 jsonl replay (до C3 playlist на FM2)."""
    staging = repo_root() / "tmp" / "play_inference" / f"ep{episode:04d}"
    tmp = staging / "tmp"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    env = os.environ.copy()
    if overlay_path and overlay_path.is_file():
        env["WAIT_ACHIEVEMENT_OVERLAY"] = str(overlay_path.resolve())
    if block_label:
        env["WAIT_BLOCK_LABEL"] = block_label
    _playback_ram_env(args.game, args.mission, env)

    frames = replay_frame_count(jsonl_path, episode)
    hold = _overlay_hold_frames(overlay_path)
    timeout = max(args.timeout, (frames + hold) / 30.0 + 15.0)

    print(f"Playing episode {episode} from {jsonl_path.name} ({frames} frames, jsonl)", flush=True)
    run_inference_playback(
        jsonl_path=jsonl_path,
        episode=episode,
        staging=staging,
        tmp_dir=tmp,
        overlay_path=overlay_path,
        timeout_sec=timeout,
        turbo=args.turbo,
        game=args.game,
        mission=args.mission,
        extra_env=env,
    )


def _play_playlist(args: argparse.Namespace, playlist_path: Path) -> None:
    logs_dir = playlist_path.parent
    playlist = json.loads(playlist_path.read_text(encoding="utf-8"))
    clips = playlist.get("clips") or []
    if not clips:
        raise SystemExit(f"Playlist has no clips: {playlist_path}")

    print(f"Playlist {playlist_path.name}: {len(clips)} clip(s)", flush=True)
    for clip_idx, clip in enumerate(clips, start=1):
        fm2_name = clip.get("fm2") or clip.get("fm2_path")
        if fm2_name:
            fm2 = Path(fm2_name)
            if not fm2.is_file():
                fm2 = logs_dir / Path(fm2_name).name
            if not fm2.is_file():
                raise SystemExit(f"FM2 not found for playlist clip: {fm2_name}")
            overlay_name = clip.get("overlay")
            if overlay_name:
                args.overlay = str(logs_dir / overlay_name)
            if clip.get("block_label"):
                os.environ["WAIT_BLOCK_LABEL"] = str(clip["block_label"])
            print(
                f"  clip {clip_idx}/{len(clips)}: {fm2.name} ({clip.get('block_label', '')})",
                flush=True,
            )
            _play_single_fm2(args, fm2.resolve())
            continue

        inputs_name = clip.get("inference_inputs")
        if not inputs_name:
            raise SystemExit(f"Clip missing fm2/inference_inputs: {clip}")
        jsonl_path = logs_dir / inputs_name
        episode = int(clip.get("episode", -1))
        overlay_name = clip.get("overlay")
        overlay_path = logs_dir / overlay_name if overlay_name else None
        print(
            f"  clip {clip_idx}/{len(clips)}: ep={episode} jsonl ({clip.get('block_label', '')})",
            flush=True,
        )
        _play_episode_jsonl(
            args,
            jsonl_path=jsonl_path,
            episode=episode,
            overlay_path=overlay_path if overlay_path and overlay_path.is_file() else None,
            block_label=clip.get("block_label"),
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Play inference FM2 (-playmovie) or playlist/jsonl"
    )
    parser.add_argument(
        "input",
        nargs="?",
        help=".fm2 | YYYYMMDD_playlist.json | опустить при --inputs + --episode",
    )
    parser.add_argument("--game", default="rushn_attack")
    parser.add_argument("--mission", default="m1")
    parser.add_argument("--inputs", type=Path, default=None, help="jsonl (legacy)")
    parser.add_argument("--episode", type=int, default=None)
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

    if args.inputs and args.episode is not None:
        jsonl = _resolve_input_path(args.inputs, args.game, args.mission)
        overlay = _resolve_input_path(args.overlay, args.game, args.mission) if args.overlay else None
        _play_episode_jsonl(args, jsonl_path=jsonl, episode=args.episode, overlay_path=overlay)
        return

    if not args.input:
        raise SystemExit("Provide .fm2, playlist.json, or --inputs + --episode")

    input_path = _resolve_input_path(Path(args.input), args.game, args.mission)
    if not input_path.is_file():
        raise SystemExit(f"Input not found: {input_path}")

    if input_path.suffix.lower() == ".fm2":
        _play_single_fm2(args, input_path)
        return

    if input_path.suffix.lower() == ".json" and input_path.name.endswith("_playlist.json"):
        _play_playlist(args, input_path)
        return

    raise SystemExit("Expected .fm2, YYYYMMDD_playlist.json, or --inputs + --episode")


if __name__ == "__main__":
    main()
