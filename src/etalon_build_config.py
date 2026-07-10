"""Загрузка конфига сборки эталона из плагина игры (DESIGN §2)."""
from __future__ import annotations

from project_paths import game_dir, load_yaml


def load_etalon_build_config(game_id: str) -> dict:
    game_yaml = load_yaml(game_dir(game_id) / "game.yaml")
    rel = game_yaml.get("etalon_build_config", "etalon_build.yaml")
    path = game_dir(game_id) / rel
    if not path.is_file():
        raise FileNotFoundError(
            f"Etalon build config not found: {path} (set etalon_build_config in game.yaml)"
        )
    return load_yaml(path)


def transition_rooms_from_etalon_build(etalon_build: dict) -> frozenset[int]:
    raw = etalon_build.get("transition_rooms")
    if not raw:
        raise ValueError("etalon_build.yaml: transition_rooms is required")
    return frozenset(int(str(r), 16) for r in raw)


def checkpoint_names_from_etalon_build(etalon_build: dict) -> tuple[str, ...]:
    names = etalon_build.get("checkpoint_names") or ()
    return tuple(str(n) for n in names)


def segment_count_from_etalon_build(etalon_build: dict) -> int:
    return int(etalon_build.get("segment_count", 5))


def checkpoint_heuristics_from_etalon_build(etalon_build: dict) -> list[dict]:
    raw = etalon_build.get("checkpoint_heuristics")
    if not raw:
        raise ValueError("etalon_build.yaml: checkpoint_heuristics is required")
    return list(raw)
