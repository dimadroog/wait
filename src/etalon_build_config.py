"""Загрузка конфига сборки эталона из плагина игры (DESIGN §2)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from project_paths import game_dir, load_yaml

# require_input kinds (ядро интерпретирует; значения задаёт плагин).
REQUIRE_INPUT_NONE = "none"
REQUIRE_INPUT_MOVE_OR_ATTACK = "move_or_attack"
_KNOWN_REQUIRE_INPUT = frozenset({REQUIRE_INPUT_NONE, REQUIRE_INPUT_MOVE_OR_ATTACK})


@dataclass(frozen=True)
class GameplayStartRule:
    """Нейтральное правило поиска кадра gameplay-start (данные — из YAML плагина)."""

    exclude_transition_rooms: bool = True
    lives_min: int | None = None
    lives_max: int | None = None
    require_input: str = REQUIRE_INPUT_NONE

    def __post_init__(self) -> None:
        if self.require_input not in _KNOWN_REQUIRE_INPUT:
            raise ValueError(
                f"etalon_build.gameplay_start.require_input must be one of "
                f"{sorted(_KNOWN_REQUIRE_INPUT)}, got {self.require_input!r}"
            )
        if (self.lives_min is None) ^ (self.lives_max is None):
            raise ValueError(
                "etalon_build.gameplay_start: set both lives_min and lives_max, or neither"
            )
        if self.lives_min is not None and self.lives_max is not None:
            if int(self.lives_min) > int(self.lives_max):
                raise ValueError("etalon_build.gameplay_start: lives_min > lives_max")


def load_etalon_build_config(game_id: str) -> dict | None:
    """Опциональный YAML сборки эталона.

    Нет файла / ключа — ``None``: якоря ``head_save_states`` + ручной ``routes.yaml``.
    """
    game_yaml = load_yaml(game_dir(game_id) / "game.yaml")
    rel = game_yaml.get("etalon_build_config") or "etalon_build.yaml"
    path = game_dir(game_id) / rel
    if not path.is_file():
        return None
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


def gameplay_start_rule_from_etalon_build(etalon_build: dict) -> GameplayStartRule:
    """Правило gameplay-start из плагина; если секции нет — только exclude transition."""
    raw = etalon_build.get("gameplay_start") or {}
    if not isinstance(raw, dict):
        raise ValueError("etalon_build.yaml: gameplay_start must be a mapping")
    lives_min = raw.get("lives_min")
    lives_max = raw.get("lives_max")
    return GameplayStartRule(
        exclude_transition_rooms=bool(raw.get("exclude_transition_rooms", True)),
        lives_min=None if lives_min is None else int(lives_min),
        lives_max=None if lives_max is None else int(lives_max),
        require_input=str(raw.get("require_input") or REQUIRE_INPUT_NONE),
    )


def rewards_default_from_etalon_build(etalon_build: dict) -> dict[str, Any]:
    """Блок rewards.default для генерации routes.yaml (плагин или пустой → минимальный каркас)."""
    raw = etalon_build.get("rewards_default")
    if raw is None:
        return {
            "checkpoint_bonus": 100,
            "death_penalty": 40,
            "mission_clear_bonus": 1000,
            "step_penalty": 0.005,
            "kill_bonus": 0,
        }
    if not isinstance(raw, dict):
        raise ValueError("etalon_build.yaml: rewards_default must be a mapping")
    return {
        "checkpoint_bonus": float(raw.get("checkpoint_bonus", 100)),
        "death_penalty": float(raw.get("death_penalty", 40)),
        "mission_clear_bonus": float(raw.get("mission_clear_bonus", 1000)),
        "step_penalty": float(raw.get("step_penalty", 0.005)),
        "kill_bonus": float(raw.get("kill_bonus", 0)),
    }
