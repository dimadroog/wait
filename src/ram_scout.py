"""RAM-разведка: FM2 → FCEUX/Lua → jsonl → candidates (и опционально ram_resolve)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from fceux_launch import fceux_sound_off
from project_paths import (
    count_fm2_frames,
    game_ram_scout_candidates_path,
    game_ram_scout_jsonl_path,
    game_scout_dir,
    mission_scout_dir,
    parse_fm2_rom_basename,
    ram_resolve_path,
    ram_scout_candidates_path,
    ram_scout_jsonl_path,
    repo_root,
    resolve_fceux_binary,
    resolve_rom,
)
from ram_resolve import (
    FieldPick,
    build_candidates,
    collect_stats,
    load_frames,
    run_resolve,
    write_candidates,
)


@dataclass(frozen=True)
class ScoutPaths:
    jsonl: Path
    candidates: Path
    staging: Path
    config_path: Path
    do_resolve: bool


@dataclass
class ScoutResult:
    jsonl: Path
    candidates: Path
    scope: str
    round_id: str
    mission: Path | None
    picks: list[FieldPick]
    wrote_resolve: bool


def stage_fm2(fm2: Path, rom: Path, staging: Path) -> tuple[Path, Path]:
    """Скопировать FM2 и ROM в staging; вернуть (staged_fm2, staged_rom)."""
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
    with fceux_sound_off(fceux_dir):
        yield


def run_fceux_scout(
    staged_fm2: Path,
    staged_rom: Path,
    config_path: Path,
    timeout_sec: float,
) -> None:
    """Запустить FCEUX с ram_scout.lua до done_flag или таймаута."""
    fceux = resolve_fceux_binary()
    lua = repo_root() / "fceux" / "lua" / "ram_scout.lua"
    env = os.environ.copy()
    env["WAIT_RAM_SCOUT_CONFIG"] = str(config_path)

    done_flag = Path(json.loads(config_path.read_text(encoding="utf-8"))["done_flag"])
    if done_flag.exists():
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


def write_candidates_only(jsonl: Path, candidates: Path) -> None:
    frames = load_frames(jsonl)
    stats = collect_stats(frames)
    write_candidates(candidates, len(frames), build_candidates(stats))


def prepare_scout_paths(
    *,
    game_id: str,
    scope: str,
    mission: Path | None,
    round_id: str,
    write_ram_map: bool,
) -> ScoutPaths:
    """Каталоги jsonl/candidates/staging; mission resolve только при write_ram_map."""
    if scope == "shell":
        scout_dir = game_scout_dir(game_id, round_id)
        scout_dir.mkdir(parents=True, exist_ok=True)
        jsonl = game_ram_scout_jsonl_path(game_id, round_id)
        candidates = game_ram_scout_candidates_path(game_id, round_id)
        do_resolve = False
    else:
        if mission is None:
            raise ValueError("mission scope requires mission Path")
        mission_scout_dir(mission).mkdir(parents=True, exist_ok=True)
        ram_resolve_path(mission).parent.mkdir(parents=True, exist_ok=True)
        jsonl = ram_scout_jsonl_path(mission)
        candidates = ram_scout_candidates_path(mission)
        do_resolve = bool(write_ram_map)

    staging = repo_root() / "tmp" / "ram_scout" / "staging"
    config_path = repo_root() / "tmp" / "ram_scout" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    return ScoutPaths(
        jsonl=jsonl,
        candidates=candidates,
        staging=staging,
        config_path=config_path,
        do_resolve=do_resolve,
    )


def run_ram_scout(
    *,
    fm2: Path,
    game_id: str,
    scope: str,
    mission: Path | None,
    round_id: str | None = None,
    timeout: float = 600.0,
    write_ram_map: bool = False,
    run_fceux: bool = True,
    log: Callable[[str], None] | None = print,
) -> ScoutResult:
    """Прогнать scout: staging → FCEUX → candidates (и опционально resolve).

    run_fceux=False — только подготовка путей/config (тесты без эмулятора).
    """
    rid = round_id if round_id is not None else fm2.stem
    rom = resolve_rom(game_id)
    paths = prepare_scout_paths(
        game_id=game_id,
        scope=scope,
        mission=mission,
        round_id=rid,
        write_ram_map=write_ram_map,
    )

    frames = count_fm2_frames(fm2)
    timeout_sec = max(timeout, frames / 30.0 + 60.0)

    staged_fm2, staged_rom = stage_fm2(fm2, rom, paths.staging)
    paths.config_path.write_text(
        json.dumps(
            {
                "output_jsonl": str(paths.jsonl.resolve()),
                "done_flag": str((paths.config_path.parent / "done.flag").resolve()),
            }
        ),
        encoding="utf-8",
    )

    if log is not None:
        for line in scout_progress_lines(
            fm2=fm2,
            frames=frames,
            scope=scope,
            round_id=rid,
            staging=paths.staging,
            jsonl=paths.jsonl,
        ):
            log(line)

    if run_fceux:
        run_fceux_scout(staged_fm2, staged_rom, paths.config_path, timeout_sec)

    picks: list[FieldPick] = []
    if paths.do_resolve:
        if mission is None:
            raise ValueError("write_ram_map requires mission")
        picks = run_resolve(paths.jsonl, mission)
    elif paths.jsonl.is_file():
        write_candidates_only(paths.jsonl, paths.candidates)

    return ScoutResult(
        jsonl=paths.jsonl,
        candidates=paths.candidates,
        scope=scope,
        round_id=rid,
        mission=mission,
        picks=picks,
        wrote_resolve=paths.do_resolve,
    )


def format_scout_summary(result: ScoutResult) -> list[str]:
    """Строки отчёта для CLI."""
    lines = [
        f"Done: {result.jsonl}",
        f"Candidates: {result.candidates}",
    ]
    if result.wrote_resolve and result.mission is not None:
        resolve_json = ram_resolve_path(result.mission)
        lines.append(f"Resolve: {resolve_json}")
        for p in result.picks:
            if p.addr is not None:
                lines.append(f"  {p.name}: 0x{p.addr:04X} (confidence {p.confidence})")
            else:
                lines.append(f"  {p.name}: unresolved")
        lines.append(f"RAM map: {result.mission / 'ram_map.md'}")
    elif result.scope == "shell":
        lines.append("Shell round: raw scout only (copy anchors into env_config.yaml manually)")
    return lines


def scout_progress_lines(
    *,
    fm2: Path,
    frames: int,
    scope: str,
    round_id: str,
    staging: Path,
    jsonl: Path,
) -> list[str]:
    return [
        f"FM2: {fm2} ({frames} frames)",
        f"Scope: {scope}  round: {round_id}",
        f"Staging: {staging}",
        f"Output: {jsonl}",
        "Starting FCEUX...",
    ]


# re-export for typing convenience in callers
__all__ = [
    "ScoutPaths",
    "ScoutResult",
    "format_scout_summary",
    "prepare_scout_paths",
    "run_fceux_scout",
    "run_ram_scout",
    "scout_progress_lines",
    "stage_fm2",
    "write_candidates_only",
]
