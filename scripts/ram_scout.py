#!/usr/bin/env python3
"""RAM-разведка: FM2 в FCEUX → jsonl → candidates → авто-resolve → ram_map.md."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from project_paths import (  # noqa: E402
    count_fm2_frames,
    mission_scout_dir,
    parse_fm2_rom_basename,
    ram_resolve_path,
    ram_scout_candidates_path,
    ram_scout_jsonl_path,
    repo_root,
    resolve_fceux_binary,
    resolve_mission_fm2,
    resolve_rom,
)
from ram_resolve import run_resolve  # noqa: E402


def _stage_fm2(fm2: Path, rom: Path, staging: Path) -> tuple[Path, Path]:
    staging.mkdir(parents=True, exist_ok=True)
    staged_fm2 = staging / fm2.name
    shutil.copy2(fm2, staged_fm2)
    rom_base = parse_fm2_rom_basename(fm2)
    staged_rom = staging / rom_base
    for name in (rom_base, rom_base + ".nes", rom.name):
        shutil.copy2(rom, staging / name)
    return staged_fm2, staged_rom


@contextmanager
def _fceux_sound_off(fceux_dir: Path):
    """Временно выключает звук в fceux.cfg (parallel-safe)."""
    from fceux_launch import fceux_sound_off

    with fceux_sound_off(fceux_dir):
        yield


def _run_fceux(staged_fm2: Path, staged_rom: Path, config_path: Path, timeout_sec: float) -> None:
    fceux = resolve_fceux_binary()
    lua = repo_root() / "fceux" / "lua" / "ram_scout.lua"
    env = os.environ.copy()
    env["WAIT_RAM_SCOUT_CONFIG"] = str(config_path)

    done_flag = Path(json.loads(config_path.read_text(encoding="utf-8"))["done_flag"])
    if done_flag.exists():
        done_flag.unlink()

    # ROM — последний аргумент; FM2 — через -playmovie (не как ROM).
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
        str(lua),
        "-playmovie",
        str(staged_fm2),
        str(staged_rom),
    ]

    with _fceux_sound_off(fceux.parent):
        proc = subprocess.Popen(
            cmd,
            cwd=str(staged_fm2.parent),
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )

        deadline = time.time() + timeout_sec
        while proc.poll() is None:
            if done_flag.is_file():
                proc.wait(timeout=30)
                return
            if time.time() > deadline:
                proc.terminate()
                raise TimeoutError(f"FCEUX timeout ({timeout_sec}s)")
            time.sleep(0.2)

        if proc.returncode not in (0, None):
            raise RuntimeError(f"FCEUX exited with code {proc.returncode}")


def main() -> None:
    parser = argparse.ArgumentParser(description="RAM scout via FM2 replay")
    parser.add_argument(
        "fm2",
        help="путь к FM2: games/<game>/missions/<mission>/reference/<file>.fm2",
    )
    parser.add_argument("--timeout", type=float, default=600.0, help="секунд на проигрывание")
    parser.add_argument("--no-ram-map", action="store_true", help="не обновлять ram_map.md")
    args = parser.parse_args()

    try:
        fm2, game_id, mission = resolve_mission_fm2(args.fm2)
    except (FileNotFoundError, ValueError) as e:
        raise SystemExit(str(e)) from e

    rom = resolve_rom(game_id)
    mission_scout_dir(mission).mkdir(parents=True, exist_ok=True)
    ram_resolve_path(mission).parent.mkdir(parents=True, exist_ok=True)

    jsonl = ram_scout_jsonl_path(mission)
    candidates = ram_scout_candidates_path(mission)
    staging = repo_root() / "tmp" / "ram_scout" / "staging"
    config_path = repo_root() / "tmp" / "ram_scout" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    frames = count_fm2_frames(fm2)
    timeout = max(args.timeout, frames / 30.0 + 60.0)

    staged_fm2, staged_rom = _stage_fm2(fm2, rom, staging)
    config_path.write_text(
        json.dumps(
            {
                "output_jsonl": str(jsonl.resolve()),
                "done_flag": str((config_path.parent / "done.flag").resolve()),
            }
        ),
        encoding="utf-8",
    )

    print(f"FM2: {fm2} ({frames} frames)")
    print(f"Staging: {staging}")
    print(f"Output: {jsonl}")
    print("Starting FCEUX...")

    _run_fceux(staged_fm2, staged_rom, config_path, timeout)

    picks = run_resolve(jsonl, mission) if not args.no_ram_map else []
    if args.no_ram_map:
        from ram_resolve import build_candidates, collect_stats, load_frames, write_candidates

        frames = load_frames(jsonl)
        stats = collect_stats(frames)
        write_candidates(candidates, len(frames), build_candidates(stats))

    print(f"Done: {jsonl}")
    print(f"Candidates: {candidates}")
    if not args.no_ram_map:
        resolve_json = ram_resolve_path(mission)
        print(f"Resolve: {resolve_json}")
        for p in picks:
            if p.addr is not None:
                print(f"  {p.name}: 0x{p.addr:04X} (confidence {p.confidence})")
            else:
                print(f"  {p.name}: unresolved")
        print(f"RAM map: {mission / 'ram_map.md'}")


if __name__ == "__main__":
    main()
