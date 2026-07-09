"""Загрузка Phase 0 Strategy из плагина игры (DESIGN §2)."""
from __future__ import annotations

from project_paths import game_dir, load_yaml


def load_phase0_config(game_id: str) -> dict:
    meta = load_yaml(game_dir(game_id) / "game.yaml")
    rel = meta.get("phase0_config", "phase0.yaml")
    path = game_dir(game_id) / rel
    if not path.is_file():
        raise FileNotFoundError(
            f"Phase 0 config not found: {path} (set phase0_config in game.yaml)"
        )
    return load_yaml(path)


def transition_rooms_from_config(phase0: dict) -> frozenset[int]:
    raw = phase0.get("transition_rooms")
    if not raw:
        raise ValueError("phase0.yaml: transition_rooms is required")
    return frozenset(int(str(r), 16) for r in raw)


def checkpoint_names_from_config(phase0: dict) -> tuple[str, ...]:
    names = phase0.get("checkpoint_names") or ()
    return tuple(str(n) for n in names)


def segment_count_from_config(phase0: dict) -> int:
    return int(phase0.get("segment_count", 5))


def checkpoint_heuristics_from_config(phase0: dict) -> list[dict]:
    raw = phase0.get("checkpoint_heuristics")
    if not raw:
        raise ValueError("phase0.yaml: checkpoint_heuristics is required")
    return list(raw)
