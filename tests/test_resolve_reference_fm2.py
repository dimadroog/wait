"""resolve_reference_fm2: shell vs mission layouts (без FCEUX)."""
from __future__ import annotations

from pathlib import Path

import pytest

from project_paths import (
    game_ram_scout_jsonl_path,
    game_reference_dir,
    game_scout_dir,
    resolve_mission_fm2,
    resolve_reference_fm2,
    repo_root,
)


def test_resolve_mission_clear_fm2() -> None:
    rel = "games/rushn_attack/missions/m1/reference/clear.fm2"
    fm2, game_id, scope, mission = resolve_reference_fm2(rel)
    assert game_id == "rushn_attack"
    assert scope == "mission"
    assert mission == repo_root() / "games" / "rushn_attack" / "missions" / "m1"
    assert fm2 == mission / "reference" / "clear.fm2"
    p2, g2, m2 = resolve_mission_fm2(rel)
    assert (p2, g2, m2) == (fm2, game_id, mission)


def test_resolve_shell_game_over_fm2() -> None:
    rel = "games/rushn_attack/reference/game_over_to_attract.fm2"
    fm2, game_id, scope, mission = resolve_reference_fm2(rel)
    assert game_id == "rushn_attack"
    assert scope == "shell"
    assert mission is None
    assert fm2.parent == game_reference_dir("rushn_attack")
    assert fm2.name == "game_over_to_attract.fm2"


def test_resolve_mission_fm2_rejects_shell_path() -> None:
    with pytest.raises(ValueError, match="missions"):
        resolve_mission_fm2("games/rushn_attack/reference/game_over_to_attract.fm2")


def test_resolve_rejects_missing_and_wrong_layout(tmp_path: Path) -> None:
    missing = repo_root() / "games" / "rushn_attack" / "reference" / "no_such.fm2"
    with pytest.raises(FileNotFoundError):
        resolve_reference_fm2(missing)

    # games/<g>/rom/<file>.fm2 — не shell и не mission reference
    rogue = tmp_path / "games" / "rushn_attack" / "rom" / "clip.fm2"
    rogue.parent.mkdir(parents=True)
    rogue.write_text("|0|........|\n", encoding="utf-8")
    # путь вне repo_root()/games — index("games") всё же найдёт сегмент
    with pytest.raises(ValueError, match="FM2 path must be"):
        resolve_reference_fm2(rogue)


def test_game_scout_paths_use_round_id() -> None:
    d = game_scout_dir("rushn_attack", "game_over_to_attract")
    assert d == game_reference_dir("rushn_attack") / "scout" / "game_over_to_attract"
    assert game_ram_scout_jsonl_path("rushn_attack", "game_over_to_attract") == (
        d / "ram_scout.jsonl"
    )
    with pytest.raises(ValueError, match="round id"):
        game_scout_dir("rushn_attack", "   ")
