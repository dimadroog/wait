"""G7: achievements YAML живёт в плагине games/<id>/."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from achievements.evaluator import achievements_config_path, load_achievements_config
from achievements.playlist import _sort_key_for_slug


def test_load_from_plugin_game_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    games = tmp_path / "games" / "demo_game"
    games.mkdir(parents=True)
    (games / "game.yaml").write_text(
        yaml.safe_dump({"game_id": "demo_game", "achievements": "noms.yaml"}),
        encoding="utf-8",
    )
    (games / "noms.yaml").write_text(
        yaml.safe_dump(
            {
                "nominations": [
                    {"slug": "clear", "idx": 1, "type": "instant", "condition": {"mission_clear": True}}
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "achievements.evaluator.game_dir",
        lambda game_id: tmp_path / "games" / game_id,
    )
    path = achievements_config_path("demo_game")
    assert path == games / "noms.yaml"
    cfg = load_achievements_config(game_id="demo_game")
    assert cfg["nominations"][0]["slug"] == "clear"


def test_load_requires_game_id() -> None:
    with pytest.raises(ValueError, match="game_id"):
        load_achievements_config()


def test_missing_plugin_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    games = tmp_path / "games" / "empty"
    games.mkdir(parents=True)
    (games / "game.yaml").write_text("game_id: empty\n", encoding="utf-8")
    monkeypatch.setattr(
        "achievements.evaluator.game_dir",
        lambda game_id: tmp_path / "games" / game_id,
    )
    with pytest.raises(FileNotFoundError, match="achievements"):
        load_achievements_config(game_id="empty")


def test_rushn_attack_plugin_file_exists() -> None:
    path = achievements_config_path("rushn_attack")
    assert path.is_file()
    assert "games" in path.parts and "rushn_attack" in path.parts
    cfg = load_achievements_config(game_id="rushn_attack")
    assert any(n.get("slug") == "ladder_ouch" for n in cfg.get("nominations") or [])


def test_playlist_sort_from_nomination_yaml() -> None:
    """Сортировка клипов — из playlist_sort / field, не if slug == …."""
    high = {"episode_reward": 100.0, "episode_frames": 50, "timestamp": "b"}
    low = {"episode_reward": 1.0, "episode_frames": 2, "timestamp": "a"}
    greedy = {"playlist_sort": {"field": "episode_reward", "order": "desc"}}
    assert _sort_key_for_slug("x", high, nomination=greedy) < _sort_key_for_slug(
        "x", low, nomination=greedy
    )
    fast = {"playlist_sort": {"field": "episode_frames", "order": "asc"}}
    assert _sort_key_for_slug("y", low, nomination=fast) < _sort_key_for_slug(
        "y", high, nomination=fast
    )


def test_no_slug_hardcode_in_playlist_sort_source() -> None:
    text = (
        Path(__file__).resolve().parents[1] / "src" / "achievements" / "playlist.py"
    ).read_text(encoding="utf-8")
    assert 'slug == "episode_reward"' not in text
    assert 'slug == "fastest_death"' not in text
