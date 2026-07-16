"""FM2 playback staging helpers for FCEUX CLI."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from fceux_launch import run_fceux_movie
from fm2_export import PLAYBACK_SAVESTATE_NAME, ensure_savestate_movie_guid, stage_playback_savestate
from project_paths import parse_fm2_rom_basename, repo_root


def stage_playback_fc0(
    inference_fc0: Path,
    staging: Path,
    *,
    guid: str,
    state_name: str = PLAYBACK_SAVESTATE_NAME,
) -> Path:
    """playback.fc0 из inference_cp0 + GUID клипа."""
    staging.mkdir(parents=True, exist_ok=True)
    dest = staging / state_name
    dest.write_bytes(ensure_savestate_movie_guid(inference_fc0.read_bytes(), guid))
    return dest


def fceux_playmovie_argv(
    *,
    staged_fm2: Path,
    staged_rom: Path,
) -> list[str]:
    """Self-contained FM2: -playmovie embed -readonly 1 rom."""
    return [
        "-playmovie",
        staged_fm2.name,
        "-readonly",
        "1",
        staged_rom.name,
    ]


def stage_external_playback(
    staged_fm2: Path,
    staging: Path,
    *,
    fallback_fc0: Path | None = None,
) -> Path:
    """playback.fc0 в staging из embed FM2 (или fallback .fc0)."""
    return stage_playback_savestate(
        staged_fm2,
        staging,
        fallback_fc0=fallback_fc0,
        state_name=PLAYBACK_SAVESTATE_NAME,
    )


def _stage_fm2_rom(fm2: Path, rom: Path, staging: Path) -> tuple[Path, Path]:
    staging.mkdir(parents=True, exist_ok=True)
    staged_fm2 = staging / fm2.name
    shutil.copy2(fm2, staged_fm2)
    rom_base = parse_fm2_rom_basename(fm2)
    staged_rom = staging / rom_base
    for name in (rom_base, rom_base + ".nes", rom.name):
        shutil.copy2(rom, staging / name)
    return staged_fm2, staged_rom


def probe_movie_playback(
    fm2_path: Path,
    rom: Path,
    staging: Path,
    tmp_dir: Path,
    *,
    ram: dict[str, int],
    probe_at_mf: int = 8,
    timeout_sec: float = 60.0,
) -> dict:
    """RAM-probe при -playmovie (ISSUE_INFERENCE N4)."""
    staged_fm2, staged_rom = _stage_fm2_rom(fm2_path, rom, staging)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    done_flag = tmp_dir / "done.flag"
    probe_flag = tmp_dir / "probe.json"
    for p in (done_flag, probe_flag):
        if p.exists():
            p.unlink()
    config_path = tmp_dir / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "done_flag": done_flag.resolve().as_posix(),
                "probe_flag": probe_flag.resolve().as_posix(),
                "probe_at_mf": probe_at_mf,
                **ram,
            }
        ),
        encoding="utf-8",
    )
    lua = repo_root() / "fceux" / "lua" / "movie_playback_probe.lua"
    run_fceux_movie(
        staged_fm2,
        staged_rom,
        lua,
        config_path,
        cwd=staging,
        timeout_sec=timeout_sec,
        done_flag=done_flag,
        noicon=False,
    )
    if not probe_flag.is_file():
        return {"ok": False, "error": "probe_missing"}
    return json.loads(probe_flag.read_text(encoding="utf-8"))
