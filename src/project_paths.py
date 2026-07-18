"""Пути репозитория wait/."""
from __future__ import annotations

import os
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import yaml

ARTIFACT_KINDS = frozenset({"smoke", "bench"})

_REPO_ROOT = Path(__file__).resolve().parents[1]


def repo_root() -> Path:
    return _REPO_ROOT


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def game_dir(game_id: str) -> Path:
    return repo_root() / "games" / game_id


def mission_dir(game_id: str, mission_id: str) -> Path:
    return game_dir(game_id) / "missions" / mission_id


def mission_scout_dir(mission: Path) -> Path:
    """Каталог ram_scout.jsonl и candidates (вне inference logs/)."""
    return mission / "reference" / "scout"


def ram_scout_jsonl_path(mission: Path) -> Path:
    return mission_scout_dir(mission) / "ram_scout.jsonl"


def ram_scout_candidates_path(mission: Path) -> Path:
    return mission_scout_dir(mission) / "ram_scout_candidates.json"


def ram_resolve_path(mission: Path) -> Path:
    """Целевой путь записи runtime-конфига RAM (в git)."""
    return mission / "config" / "ram_resolve.json"


def resolve_mission_fm2(fm2_arg: str | Path) -> tuple[Path, str, Path]:
    """FM2 → (файл, game_id, каталог миссии).

    Ожидаемый layout: games/<game>/missions/<mission>/reference/<file>.fm2
    Относительные пути — от корня репозитория.
    """
    p = Path(fm2_arg)
    if not p.is_absolute():
        p = repo_root() / p
    p = p.resolve()

    if not p.is_file():
        raise FileNotFoundError(f"FM2 not found: {p}")
    if p.suffix.lower() != ".fm2":
        raise ValueError(f"Not an FM2 file: {p}")

    parts = p.parts
    try:
        games_idx = parts.index("games")
    except ValueError as e:
        raise ValueError(
            "FM2 path must be games/<game>/missions/<mission>/reference/<file>.fm2"
        ) from e

    tail = parts[games_idx + 1 :]
    if len(tail) != 5 or tail[1] != "missions" or tail[3] != "reference":
        raise ValueError(
            "FM2 path must be games/<game>/missions/<mission>/reference/<file>.fm2"
        )

    game_id, mission_id = tail[0], tail[2]
    mission = mission_dir(game_id, mission_id)
    reference = mission / "reference"
    if p.parent.resolve() != reference.resolve():
        raise ValueError(f"FM2 must be in {reference.as_posix()}: {p}")

    return p, game_id, mission


def resolve_rom(game_id: str) -> Path:
    game_yaml = load_yaml(game_dir(game_id) / "game.yaml")
    rom_rel = game_yaml.get("rom_file", "rom/game.nes")
    rom = game_dir(game_id) / rom_rel
    if not rom.is_file():
        raise FileNotFoundError(f"ROM not found: {rom}")
    return rom


def resolve_fceux_home() -> Path:
    """Каталог portable FCEUX: env FCEUX_HOME или fceux/runtime.yaml → home."""
    env = os.environ.get("FCEUX_HOME")
    if env:
        home = Path(env)
        if not home.is_absolute():
            home = repo_root() / home
        return home.resolve()
    runtime = load_yaml(repo_root() / "fceux" / "runtime.yaml")
    home = Path(runtime.get("home", "fceux/portable"))
    if not home.is_absolute():
        home = repo_root() / home
    return home.resolve()


def resolve_fceux_binary() -> Path:
    home = resolve_fceux_home()
    for name in ("fceux64.exe", "fceux.exe"):
        binary = home / name
        if binary.is_file():
            return binary
    raise FileNotFoundError(f"FCEUX binary not found in {home} (tried fceux64.exe, fceux.exe)")


def parse_fm2_rom_basename(fm2_path: Path) -> str:
    with fm2_path.open(encoding="utf-8", errors="replace") as f:
        for _ in range(32):
            line = f.readline()
            if not line:
                break
            if line.startswith("romFilename "):
                return line.split(" ", 1)[1].strip()
    return "game"


def count_fm2_frames(fm2_path: Path) -> int:
    n = 0
    with fm2_path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("|"):
                n += 1
    return n


def artifact_quarantine_dir(kind: str, session: str) -> Path:
    """Карантин временных артефактов: tmp/{kind}/{session}/ (gitignored).

    Единственный допустимый каталог для вывода smoke/benchmark (кроме stdout).
    """
    if kind not in ARTIFACT_KINDS:
        raise ValueError(f"artifact kind must be one of {sorted(ARTIFACT_KINDS)}: {kind!r}")
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in session.strip())
    if not safe:
        raise ValueError("artifact session id must be non-empty")
    path = repo_root() / "tmp" / kind / safe
    path.mkdir(parents=True, exist_ok=True)
    return path


def cleanup_artifact_quarantine(kind: str | None = None, session: str | None = None) -> None:
    """Удалить tmp/smoke|bench[/session]. kind=None — оба kind; session=None — весь kind."""
    root = repo_root() / "tmp"
    kinds = [kind] if kind else sorted(ARTIFACT_KINDS)
    for k in kinds:
        if k not in ARTIFACT_KINDS:
            raise ValueError(f"unknown artifact kind: {k!r}")
        base = root / k
        if not base.is_dir():
            continue
        if session is None:
            shutil.rmtree(base, ignore_errors=True)
            continue
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in session.strip())
        target = base / safe
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)


@contextmanager
def artifact_session(kind: str, session: str) -> Iterator[Path]:
    """Контекст: tmp/{kind}/{session}/ с удалением каталога в finally."""
    path = artifact_quarantine_dir(kind, session)
    try:
        yield path
    finally:
        cleanup_artifact_quarantine(kind, session)


def default_model_zip(mission: Path, generation: int = 0) -> Path:
    """Канонический zip поколения модели: models/gen{N}.zip относительно миссии."""
    return mission / "models" / f"gen{int(generation)}.zip"


def save_states_dir(mission: Path) -> Path:
    """Каталог FCEUX save states миссии (cpN.fc0, inference_cp0.fc0)."""
    return mission / "save_states"


def demos_for_bc_dir(mission: Path) -> Path:
    """Каталог BC-демо (эталон → NPZ): reference/demos_for_bc/."""
    return mission / "reference" / "demos_for_bc"


def default_save_state_rel(cp_index: int = 0) -> str:
    """Путь save state относительно миссии: save_states/cpN.fc0."""
    return f"save_states/cp{int(cp_index)}.fc0"


def _mission_model_dirs(mission: Path) -> list[Path]:
    dirs = [mission / "models", mission / "models" / "runs"]
    return [d for d in dirs if d.is_dir()]


def cleanup_mission_smoke_models(mission: Path) -> list[Path]:
    """Удалить smoke_* в models/ и models/runs/ (ошибочные прогоны train/smoke)."""
    removed: list[Path] = []
    for base in _mission_model_dirs(mission):
        for path in base.glob("smoke_*"):
            if path.is_file():
                path.unlink()
                removed.append(path)
    return removed


def find_stray_smoke_artifacts(mission: Path) -> list[Path]:
    """Пути smoke_* в games/.../models — не должны оставаться после сессии."""
    found: list[Path] = []
    for base in _mission_model_dirs(mission):
        found.extend(p for p in base.glob("smoke_*") if p.is_file())
    return sorted(found)
