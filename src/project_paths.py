"""Пути репозитория wait/."""
from __future__ import annotations

import argparse
import os
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Literal

import yaml

ARTIFACT_KINDS = frozenset({"smoke", "bench"})
ScoutScope = Literal["shell", "mission"]

_REPO_ROOT = Path(__file__).resolve().parents[1]
_GAME_MISSION_HELP = "default: config/workspace.yaml; иначе обязателен CLI"


def repo_root() -> Path:
    return _REPO_ROOT


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def workspace_config_path() -> Path:
    """Путь к конфигу рабочей области (дефолты game/mission для CLI)."""
    return repo_root() / "config" / "workspace.yaml"


def load_workspace(path: Path | None = None) -> dict:
    """Прочитать workspace.yaml. Нет файла → {}. Не смотрит Path.cwd()."""
    cfg = path if path is not None else workspace_config_path()
    if not cfg.is_file():
        return {}
    data = load_yaml(cfg)
    return data if isinstance(data, dict) else {}


def _nonempty_str(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def resolve_game_mission(
    game: str | None = None,
    mission: str | None = None,
    *,
    workspace_path: Path | None = None,
) -> tuple[str, str]:
    """CLI > workspace.yaml > SystemExit. cwd не влияет на выбор плагина."""
    ws = load_workspace(workspace_path)
    resolved_game = _nonempty_str(game) or _nonempty_str(ws.get("game"))
    resolved_mission = _nonempty_str(mission) or _nonempty_str(ws.get("mission"))
    missing: list[str] = []
    if not resolved_game:
        missing.append("game")
    if not resolved_mission:
        missing.append("mission")
    if missing:
        cfg = workspace_path if workspace_path is not None else workspace_config_path()
        raise SystemExit(
            f"Не заданы {', '.join(missing)}: укажите --game/--mission "
            f"или заполните {cfg.as_posix()}"
        )
    return resolved_game, resolved_mission


def add_game_mission_arguments(parser: argparse.ArgumentParser) -> None:
    """--game / --mission с default=None (резолв через apply_resolved_game_mission)."""
    parser.add_argument("--game", default=None, help=f"game id ({_GAME_MISSION_HELP})")
    parser.add_argument("--mission", default=None, help=f"mission id ({_GAME_MISSION_HELP})")


def apply_resolved_game_mission(
    args: Any,
    *,
    workspace_path: Path | None = None,
) -> tuple[str, str]:
    """Записать args.game / args.mission из CLI или workspace; вернуть пару."""
    game, mission = resolve_game_mission(
        getattr(args, "game", None),
        getattr(args, "mission", None),
        workspace_path=workspace_path,
    )
    args.game = game
    args.mission = mission
    return game, mission


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


def route_triggers_path(mission: Path) -> Path:
    """Скомпилированные RAM-триггеры CP (производный артефакт, фаза E′)."""
    return mission / "config" / "route_triggers.yaml"


def game_reference_dir(game_id: str) -> Path:
    """Shell-клипы и scout раундов оболочки: games/<game>/reference/."""
    return game_dir(game_id) / "reference"


def game_scout_dir(game_id: str, round_id: str) -> Path:
    """Сырой scout shell-раунда: games/<game>/reference/scout/<round_id>/."""
    safe = _safe_round_id(round_id)
    return game_reference_dir(game_id) / "scout" / safe


def game_ram_scout_jsonl_path(game_id: str, round_id: str) -> Path:
    return game_scout_dir(game_id, round_id) / "ram_scout.jsonl"


def game_ram_scout_candidates_path(game_id: str, round_id: str) -> Path:
    return game_scout_dir(game_id, round_id) / "ram_scout_candidates.json"


def _safe_round_id(round_id: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in round_id.strip())
    if not safe:
        raise ValueError("round id must be non-empty")
    return safe


def _normalize_fm2_path(fm2_arg: str | Path) -> Path:
    """Абсолютный путь к FM2; относительный — всегда от repo_root(), не от cwd."""
    p = Path(fm2_arg)
    if not p.is_absolute():
        p = repo_root() / p
    p = p.resolve()
    if not p.is_file():
        raise FileNotFoundError(f"FM2 not found: {p}")
    if p.suffix.lower() != ".fm2":
        raise ValueError(f"Not an FM2 file: {p}")
    return p


def resolve_mission_fm2(fm2_arg: str | Path) -> tuple[Path, str, Path]:
    """FM2 → (файл, game_id, каталог миссии).

    Ожидаемый layout: games/<game>/missions/<mission>/reference/<file>.fm2
    Относительные пути — от корня репозитория (не Path.cwd()).
    """
    p, game_id, scope, mission = resolve_reference_fm2(fm2_arg)
    if scope != "mission" or mission is None:
        raise ValueError(
            "FM2 path must be games/<game>/missions/<mission>/reference/<file>.fm2"
        )
    return p, game_id, mission


def _assert_fm2_matches_explicit_cli(
    game_id: str,
    scope: ScoutScope,
    mission: Path | None,
    *,
    game: str | None,
    mission_id: str | None,
) -> None:
    """Явные --game/--mission должны совпадать с layout FM2; workspace сюда не подставлять."""
    cli_game = _nonempty_str(game)
    cli_mission = _nonempty_str(mission_id)
    if cli_game and cli_game != game_id:
        raise SystemExit(
            f"--game {cli_game!r} не совпадает с игрой FM2 {game_id!r} "
            "(scope по пути файла, не по cwd)"
        )
    if cli_mission:
        if scope != "mission" or mission is None:
            raise SystemExit(
                f"--mission {cli_mission!r} задан, но FM2 — shell-layout "
                f"(games/<game>/reference/), без миссии"
            )
        if mission.name != cli_mission:
            raise SystemExit(
                f"--mission {cli_mission!r} не совпадает с миссией FM2 {mission.name!r}"
            )


def resolve_cli_reference_fm2(
    fm2_arg: str | Path | None,
    *,
    game: str | None = None,
    mission: str | None = None,
    default_fm2_name: str = "clear.fm2",
    workspace_path: Path | None = None,
) -> tuple[Path, str, ScoutScope, Path | None]:
    """Scout/entry: scope по пути FM2, иначе workspace mission + default_fm2_name.

    - Относительный FM2 — от ``repo_root()``, не от ``Path.cwd()``.
    - Явные ``--game``/``--mission`` при переданном FM2 только проверяют совпадение.
    - Без FM2: ``resolve_game_mission`` → ``missions/<m>/reference/<default_fm2_name>``.
    - ``cwd=`` у subprocess FCEUX (staging) сюда не относится.
    """
    if fm2_arg is not None and str(fm2_arg).strip():
        fm2, game_id, scope, mission_path = resolve_reference_fm2(fm2_arg)
        _assert_fm2_matches_explicit_cli(
            game_id, scope, mission_path, game=game, mission_id=mission
        )
        return fm2, game_id, scope, mission_path

    resolved_game, resolved_mission = resolve_game_mission(
        game, mission, workspace_path=workspace_path
    )
    default_path = (
        mission_dir(resolved_game, resolved_mission) / "reference" / default_fm2_name
    )
    return resolve_reference_fm2(default_path)


def resolve_cli_mission_fm2(
    fm2_arg: str | Path | None,
    *,
    game: str | None = None,
    mission: str | None = None,
    default_fm2_name: str = "clear.fm2",
    workspace_path: Path | None = None,
) -> tuple[Path, str, Path]:
    """Как resolve_cli_reference_fm2, но только mission-layout."""
    fm2, game_id, scope, mission_path = resolve_cli_reference_fm2(
        fm2_arg,
        game=game,
        mission=mission,
        default_fm2_name=default_fm2_name,
        workspace_path=workspace_path,
    )
    if scope != "mission" or mission_path is None:
        raise SystemExit(
            "Нужен mission FM2: games/<game>/missions/<mission>/reference/<file>.fm2 "
            "(или опустите путь — возьмётся clear.fm2 из workspace)"
        )
    return fm2, game_id, mission_path


def resolve_reference_fm2(
    fm2_arg: str | Path,
) -> tuple[Path, str, ScoutScope, Path | None]:
    """FM2 → (файл, game_id, scope, каталог миссии | None).

    Допустимые layout:
    - mission: games/<game>/missions/<mission>/reference/<file>.fm2
    - shell:   games/<game>/reference/<file>.fm2

    Относительные пути — от корня репозитория, не от cwd.
    """
    p = _normalize_fm2_path(fm2_arg)

    parts = p.parts
    try:
        games_idx = parts.index("games")
    except ValueError as e:
        raise ValueError(
            "FM2 path must be games/<game>/reference/<file>.fm2 or "
            "games/<game>/missions/<mission>/reference/<file>.fm2"
        ) from e

    tail = parts[games_idx + 1 :]
    # games/<g>/reference/<file>.fm2
    if len(tail) == 3 and tail[1] == "reference":
        game_id = tail[0]
        reference = game_reference_dir(game_id)
        if p.parent.resolve() != reference.resolve():
            raise ValueError(f"FM2 must be in {reference.as_posix()}: {p}")
        return p, game_id, "shell", None

    # games/<g>/missions/<m>/reference/<file>.fm2
    if len(tail) == 5 and tail[1] == "missions" and tail[3] == "reference":
        game_id, mission_id = tail[0], tail[2]
        mission = mission_dir(game_id, mission_id)
        reference = mission / "reference"
        if p.parent.resolve() != reference.resolve():
            raise ValueError(f"FM2 must be in {reference.as_posix()}: {p}")
        return p, game_id, "mission", mission

    raise ValueError(
        "FM2 path must be games/<game>/reference/<file>.fm2 or "
        "games/<game>/missions/<mission>/reference/<file>.fm2"
    )


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
    """Каталог FCEUX save states миссии (cp_<head><i>.fc0)."""
    return mission / "save_states"


def clear_save_state_files(
    states_dir: Path,
    plan: list[dict],
    *,
    replace_all: bool = False,
) -> list[Path]:
    """Удалить .fc0 перед пересъёмкой: слоты плана, или все при replace_all.

    Без ``replace_all`` чужие `.fc0` (не из plan) сохраняются.
    """
    states_dir.mkdir(parents=True, exist_ok=True)
    planned = {str(entry.get("file", "")) for entry in plan if entry.get("file")}
    removed: list[Path] = []
    if replace_all:
        targets = sorted(states_dir.glob("*.fc0"))
    else:
        targets = [states_dir / name for name in sorted(planned) if name]
    for path in targets:
        if path.is_file():
            path.unlink()
            removed.append(path)
    if not replace_all:
        extras = [p for p in states_dir.glob("*.fc0") if p.name not in planned]
        if extras:
            names = ", ".join(p.name for p in extras[:8])
            more = "" if len(extras) <= 8 else f" (+{len(extras) - 8})"
            print(
                f"  keep {len(extras)} non-plan .fc0 ({names}{more}); "
                "pass --replace-states to wipe all"
            )
    return removed


def demos_for_bc_dir(mission: Path) -> Path:
    """Каталог BC-демо (эталон → NPZ): reference/demos_for_bc/."""
    return mission / "reference" / "demos_for_bc"


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
