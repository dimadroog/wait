"""Сохранение FCEUX save states по кадрам FM2 (Phase 0 / inference)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from fceux_helpers import run_fceux_movie
from project_paths import load_yaml, parse_fm2_rom_basename, repo_root


def stage_fm2_for_fceux(fm2: Path, rom: Path, staging: Path) -> tuple[Path, Path]:
    staging.mkdir(parents=True, exist_ok=True)
    staged_fm2 = staging / fm2.name
    shutil.copy2(fm2, staged_fm2)
    rom_base = parse_fm2_rom_basename(fm2)
    staged_rom = staging / rom_base
    for name in (rom_base, rom_base + ".nes", rom.name):
        shutil.copy2(rom, staging / name)
    return staged_fm2, staged_rom


def _fceux_fcs_dir() -> Path:
    runtime = load_yaml(repo_root() / "fceux" / "runtime.yaml")
    home = runtime.get("home", "fceux/portable")
    return repo_root() / home / "fcs"


def collect_slot_states(mission: Path, fm2: Path, plan: list[dict], rom_base: str) -> None:
    """Копирует save states из fceux/portable/fcs/ в mission/states/."""
    states = mission / "states"
    states.mkdir(parents=True, exist_ok=True)
    fcs_dir = _fceux_fcs_dir()
    movie_stem = fm2.stem
    for entry in plan:
        slot = entry["slot"]
        dest = states / entry["file"]
        found = False
        for pattern in (
            f"{rom_base}.{movie_stem}.fc{slot}",
            f"{rom_base}.{movie_stem}.fc{slot}.*",
            f"{rom_base}.*.fc{slot}",
        ):
            for src in fcs_dir.glob(pattern):
                shutil.copy2(src, dest)
                found = True
                print(f"  {src.name} -> states/{dest.name}")
                break
            if found:
                break
        if not found:
            print(
                f"  warning: save state not found for slot {slot} -> {dest.name} "
                f"(looked in {fcs_dir})"
            )


def save_fm2_states(
    mission: Path,
    fm2: Path,
    rom: Path,
    plan: list[dict],
    *,
    timeout_sec: float,
    staging_subdir: str,
    tmp_subdir: str,
) -> None:
    """Проигрывает FM2 в FCEUX и сохраняет states по plan (save_states.lua)."""
    if not plan:
        return
    states = mission / "states"
    states.mkdir(parents=True, exist_ok=True)
    staging = repo_root() / "tmp" / staging_subdir / "staging"
    staged_fm2, staged_rom = stage_fm2_for_fceux(fm2, rom, staging)
    tmp = repo_root() / "tmp" / tmp_subdir
    tmp.mkdir(parents=True, exist_ok=True)
    config_path = tmp / "config.json"
    done_flag = tmp / "done.flag"
    if done_flag.exists():
        done_flag.unlink()
    config_path.write_text(
        json.dumps(
            {
                "states_dir": "states",
                "done_flag": done_flag.resolve().as_posix(),
                "save_frames": plan,
            }
        ),
        encoding="utf-8",
    )
    lua = repo_root() / "fceux" / "lua" / "save_states.lua"
    print(f"Saving {len(plan)} state(s) to {states}...")
    run_fceux_movie(
        staged_fm2,
        staged_rom,
        lua,
        config_path,
        cwd=staging,
        timeout_sec=timeout_sec,
        done_flag=done_flag,
    )
    collect_slot_states(mission, fm2, plan, parse_fm2_rom_basename(fm2))
