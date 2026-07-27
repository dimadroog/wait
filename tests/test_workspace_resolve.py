"""Резолв game/mission: CLI > workspace > SystemExit; cwd не влияет."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from project_paths import (
    apply_resolved_game_mission,
    load_workspace,
    resolve_game_mission,
    workspace_config_path,
)


def _write_workspace(path: Path, game: str | None, mission: str | None) -> Path:
    data: dict[str, str] = {}
    if game is not None:
        data["game"] = game
    if mission is not None:
        data["mission"] = mission
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def test_cli_overrides_workspace(tmp_path: Path) -> None:
    ws = _write_workspace(tmp_path / "workspace.yaml", "from_ws", "ws_m")
    assert resolve_game_mission("cli_game", "cli_m", workspace_path=ws) == (
        "cli_game",
        "cli_m",
    )


def test_partial_cli_fills_from_workspace(tmp_path: Path) -> None:
    ws = _write_workspace(tmp_path / "workspace.yaml", "ws_game", "ws_m")
    assert resolve_game_mission("cli_game", None, workspace_path=ws) == ("cli_game", "ws_m")
    assert resolve_game_mission(None, "cli_m", workspace_path=ws) == ("ws_game", "cli_m")


def test_workspace_when_cli_absent(tmp_path: Path) -> None:
    ws = _write_workspace(tmp_path / "workspace.yaml", "ws_game", "ws_m")
    assert resolve_game_mission(None, None, workspace_path=ws) == ("ws_game", "ws_m")


def test_system_exit_when_missing(tmp_path: Path) -> None:
    empty = tmp_path / "empty.yaml"
    empty.write_text("{}\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="game"):
        resolve_game_mission(None, "m1", workspace_path=empty)
    with pytest.raises(SystemExit, match="mission"):
        resolve_game_mission("g", None, workspace_path=empty)
    missing = tmp_path / "no_such.yaml"
    with pytest.raises(SystemExit, match="game"):
        resolve_game_mission(None, None, workspace_path=missing)


def test_blank_cli_treated_as_absent(tmp_path: Path) -> None:
    ws = _write_workspace(tmp_path / "workspace.yaml", "ws_game", "ws_m")
    assert resolve_game_mission("  ", "", workspace_path=ws) == ("ws_game", "ws_m")


def test_cwd_does_not_affect_resolve(tmp_path: Path) -> None:
    """Антискоуп: walk-up / cwd не выбирают плагин."""
    ws = _write_workspace(tmp_path / "workspace.yaml", "ws_game", "ws_m")
    decoy = tmp_path / "games" / "decoy" / "missions" / "m99"
    decoy.mkdir(parents=True)
    previous = Path.cwd()
    try:
        os.chdir(decoy)
        assert resolve_game_mission(None, None, workspace_path=ws) == ("ws_game", "ws_m")
        assert Path.cwd() == decoy
    finally:
        os.chdir(previous)


def test_repo_workspace_file_exists_and_loads() -> None:
    path = workspace_config_path()
    assert path.is_file()
    data = load_workspace()
    assert data.get("game")
    assert data.get("mission")


def test_apply_resolved_game_mission_mutates_namespace(tmp_path: Path) -> None:
    ws = _write_workspace(tmp_path / "workspace.yaml", "ws_game", "ws_m")

    class NS:
        game = None
        mission = None

    args = NS()
    assert apply_resolved_game_mission(args, workspace_path=ws) == ("ws_game", "ws_m")
    assert args.game == "ws_game"
    assert args.mission == "ws_m"
