"""resolve_cli_*_fm2: workspace default + explicit CLI vs path; без cwd."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from project_paths import (
    resolve_cli_mission_fm2,
    resolve_cli_reference_fm2,
    repo_root,
)


def _write_workspace(path: Path, game: str, mission: str) -> Path:
    path.write_text(
        yaml.safe_dump({"game": game, "mission": mission}, allow_unicode=True),
        encoding="utf-8",
    )
    return path


def test_omit_fm2_uses_workspace_clear(tmp_path: Path) -> None:
    ws = _write_workspace(tmp_path / "workspace.yaml", "rushn_attack", "m1")
    fm2, game_id, scope, mission = resolve_cli_reference_fm2(
        None, workspace_path=ws
    )
    assert game_id == "rushn_attack"
    assert scope == "mission"
    assert mission == repo_root() / "games" / "rushn_attack" / "missions" / "m1"
    assert fm2 == mission / "reference" / "clear.fm2"


def test_explicit_fm2_ignores_workspace_game(tmp_path: Path) -> None:
    """Явный путь FM2 задаёт scope; workspace не перебивает другую игру."""
    ws = _write_workspace(tmp_path / "workspace.yaml", "other_game", "m9")
    rel = "games/rushn_attack/reference/game_over_to_attract.fm2"
    fm2, game_id, scope, mission = resolve_cli_reference_fm2(
        rel, workspace_path=ws
    )
    assert game_id == "rushn_attack"
    assert scope == "shell"
    assert mission is None
    assert fm2.name == "game_over_to_attract.fm2"


def test_explicit_cli_conflict_with_fm2() -> None:
    rel = "games/rushn_attack/missions/m1/reference/clear.fm2"
    with pytest.raises(SystemExit, match="--game"):
        resolve_cli_reference_fm2(rel, game="other_game")
    with pytest.raises(SystemExit, match="--mission"):
        resolve_cli_reference_fm2(rel, mission="m99")
    with pytest.raises(SystemExit, match="shell"):
        resolve_cli_reference_fm2(
            "games/rushn_attack/reference/game_over_to_attract.fm2",
            mission="m1",
        )


def test_explicit_cli_matching_fm2_ok() -> None:
    rel = "games/rushn_attack/missions/m1/reference/clear.fm2"
    fm2, game_id, scope, mission = resolve_cli_reference_fm2(
        rel, game="rushn_attack", mission="m1"
    )
    assert (game_id, scope, mission.name) == ("rushn_attack", "mission", "m1")
    assert fm2.name == "clear.fm2"


def test_relative_fm2_from_repo_root_not_cwd(tmp_path: Path) -> None:
    decoy = tmp_path / "games" / "rushn_attack" / "missions" / "m1" / "reference"
    decoy.mkdir(parents=True)
    (decoy / "clear.fm2").write_text("|0|........|\n", encoding="utf-8")
    previous = Path.cwd()
    try:
        os.chdir(decoy)
        # Относительный путь от repo_root — настоящий эталон, не decoy в cwd.
        fm2, game_id, _, mission = resolve_cli_reference_fm2(
            "games/rushn_attack/missions/m1/reference/clear.fm2"
        )
        assert game_id == "rushn_attack"
        assert mission == repo_root() / "games" / "rushn_attack" / "missions" / "m1"
        assert fm2 == mission / "reference" / "clear.fm2"
        assert fm2 != (decoy / "clear.fm2").resolve()
    finally:
        os.chdir(previous)


def test_cli_mission_rejects_shell_default_path() -> None:
    with pytest.raises(SystemExit, match="mission FM2"):
        resolve_cli_mission_fm2(
            "games/rushn_attack/reference/game_over_to_attract.fm2"
        )


def test_cli_mission_omit_uses_workspace(tmp_path: Path) -> None:
    ws = _write_workspace(tmp_path / "workspace.yaml", "rushn_attack", "m1")
    fm2, game_id, mission = resolve_cli_mission_fm2(None, workspace_path=ws)
    assert game_id == "rushn_attack"
    assert mission.name == "m1"
    assert fm2.name == "clear.fm2"
