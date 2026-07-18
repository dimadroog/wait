"""Unit tests for BaseNesEnv death_mode (H3 longer episodes)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from env.base_nes_env import (
    DEATH_MODE_GAME_OVER,
    DEATH_MODE_LIFE_LOST,
    BaseNesEnv,
)


def _make_env(*, death_mode: str = DEATH_MODE_LIFE_LOST, start_lives: int = 3) -> BaseNesEnv:
    with patch("env.base_nes_env.mission_dir") as mission_dir:
        mission_dir.return_value = MagicMock()
        env = BaseNesEnv(
            game_id="rushn_attack",
            mission_id="m1",
            action_strings=("noop", "right"),
            save_state="states/cp0.fc0",
            session_id="test_death",
            death_mode=death_mode,
        )
    env._bridge = MagicMock()
    env._frames.append(np.zeros((84, 84), dtype=np.uint8))
    env._episode_start_lives = start_lives
    env._prev_lives = start_lives
    env._death_count = 0
    return env


def _step_with_lives(env: BaseNesEnv, lives: int):
    bridge = env._bridge
    bridge.step.return_value = {
        "obs_file": "x",
        "format": "raw",
        "w": 84,
        "h": 84,
        "lives": lives,
        "room": 0,
        "x": 10,
        "y": 20,
    }
    bridge.decode_obs_from_response.return_value = np.zeros((84, 84), dtype=np.uint8)
    return env.step(0)


def test_invalid_death_mode_raises() -> None:
    with pytest.raises(ValueError, match="death_mode"):
        _make_env(death_mode="nope")


def test_life_lost_terminates_on_first_death() -> None:
    env = _make_env(death_mode=DEATH_MODE_LIFE_LOST, start_lives=3)
    _obs, _r, terminated, _trunc, info = _step_with_lives(env, 0)
    assert info["died"] is True
    assert terminated is True
    assert info["death_mode"] == DEATH_MODE_LIFE_LOST


def test_game_over_continues_when_lives_hit_zero_transient() -> None:
    """RAM lives→0 на смерти — ещё не game over (нужен счётчик смертей)."""
    env = _make_env(death_mode=DEATH_MODE_GAME_OVER, start_lives=3)
    _obs, _r, terminated, _trunc, info = _step_with_lives(env, 0)
    assert info["died"] is True
    assert info["death_count"] == 1
    assert terminated is False


def test_game_over_terminates_after_budget_deaths() -> None:
    env = _make_env(death_mode=DEATH_MODE_GAME_OVER, start_lives=3)
    # death 1: 3→0 (анимация)
    _step_with_lives(env, 0)
    # respawn 2 lives left
    _step_with_lives(env, 2)
    # death 2
    _step_with_lives(env, 0)
    _step_with_lives(env, 1)
    # death 3 → budget exhausted
    _obs, _r, terminated, _trunc, info = _step_with_lives(env, 0)
    assert info["died"] is True
    assert info["death_count"] == 3
    assert terminated is True


def test_no_death_when_lives_stable() -> None:
    env = _make_env(death_mode=DEATH_MODE_GAME_OVER, start_lives=3)
    _obs, _r, terminated, _trunc, info = _step_with_lives(env, 3)
    assert info["died"] is False
    assert terminated is False
    assert info["death_count"] == 0
