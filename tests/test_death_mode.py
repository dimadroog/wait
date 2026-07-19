"""Unit tests for BaseNesEnv death_mode (H3 longer episodes)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from env.base_nes_env import (
    DEATH_MODE_GAME_OVER,
    DEATH_MODE_LIFE_LOST,
    TERMINATE_REASON_DEATH,
    TERMINATE_REASON_TITLE,
    BaseNesEnv,
)


def _make_env(
    *,
    death_mode: str = DEATH_MODE_LIFE_LOST,
    start_lives: int = 3,
    death_confirm_steps: int = 4,
    title_end_rooms: tuple[int, ...] | None = (0x00,),
    title_end_confirm_steps: int = 8,
) -> BaseNesEnv:
    with patch("env.base_nes_env.mission_dir") as mission_dir:
        mission_dir.return_value = MagicMock()
        env = BaseNesEnv(
            game_id="rushn_attack",
            mission_id="m1",
            action_strings=("noop", "right"),
            save_state="save_states/cp0.fc0",
            session_id="test_death",
            death_mode=death_mode,
            death_confirm_steps=death_confirm_steps,
            title_end_rooms=title_end_rooms,
            title_end_confirm_steps=title_end_confirm_steps,
        )
    env._bridge = MagicMock()
    env._frames.append(np.zeros((84, 84), dtype=np.uint8))
    env._episode_start_lives = start_lives
    env._prev_lives = start_lives
    env._death_count = 0
    env._title_end_streak = 0
    env._pending_lives_from = None
    env._pending_death_streak = 0
    env._left_title_pose = False
    env._title_pose_streak = 0
    env._seen_level_room = False
    env.title_pose_x = 129
    env.title_pose_confirm_steps = 45
    return env


def _step_with_lives(env: BaseNesEnv, lives: int, *, room: int = 0x06):
    bridge = env._bridge
    bridge.step.return_value = {
        "obs_file": "x",
        "format": "raw",
        "w": 84,
        "h": 84,
        "lives": lives,
        "room": room,
        "x": 10,
        "y": 20,
    }
    bridge.decode_obs_from_response.return_value = np.zeros((84, 84), dtype=np.uint8)
    return env.step(0)


def _confirm_death(
    env: BaseNesEnv,
    lives_low: int,
    *,
    room: int = 0x06,
    confirm: int | None = None,
):
    """Держать пониженные lives confirm_steps → один confirmed death."""
    n = confirm if confirm is not None else env.death_confirm_steps
    info = None
    terminated = False
    for _ in range(n):
        _obs, _r, terminated, _trunc, info = _step_with_lives(env, lives_low, room=room)
    assert info is not None
    return terminated, info


def test_invalid_death_mode_raises() -> None:
    with pytest.raises(ValueError, match="death_mode"):
        _make_env(death_mode="nope")


def test_life_lost_terminates_on_first_death() -> None:
    env = _make_env(death_mode=DEATH_MODE_LIFE_LOST, start_lives=3)
    terminated, info = _confirm_death(env, 0)
    assert info["died"] is True
    assert terminated is True
    assert info["death_mode"] == DEATH_MODE_LIFE_LOST


def test_game_over_continues_when_lives_hit_zero_transient() -> None:
    """Подтверждённая смерть ещё не game over (нужен счётчик до budget)."""
    env = _make_env(death_mode=DEATH_MODE_GAME_OVER, start_lives=3)
    terminated, info = _confirm_death(env, 0)
    assert info["died"] is True
    assert info["death_count"] == 1
    assert terminated is False


def test_room_transition_lives_flicker_is_not_death() -> None:
    """6→5→6 со streak≤3 (смена комнаты) не увеличивает death_count."""
    env = _make_env(death_mode=DEATH_MODE_GAME_OVER, start_lives=6, death_confirm_steps=4)
    for _ in range(3):
        _step_with_lives(env, 5, room=0x09)
    _obs, _r, terminated, _trunc, info = _step_with_lives(env, 6, room=0x06)
    assert info["died"] is False
    assert info["death_count"] == 0
    assert terminated is False


def test_game_over_terminates_after_budget_deaths() -> None:
    env = _make_env(death_mode=DEATH_MODE_GAME_OVER, start_lives=3)
    _confirm_death(env, 0)
    _step_with_lives(env, 2)
    _confirm_death(env, 0)
    _step_with_lives(env, 1)
    terminated, info = _confirm_death(env, 0)
    assert info["died"] is True
    assert info["death_count"] == 3
    assert terminated is True


def test_no_death_when_lives_stable() -> None:
    env = _make_env(death_mode=DEATH_MODE_GAME_OVER, start_lives=3)
    _obs, _r, terminated, _trunc, info = _step_with_lives(env, 3)
    assert info["died"] is False
    assert terminated is False
    assert info["death_count"] == 0


def test_level_death_lives_zero_does_not_title_stop() -> None:
    """Анимация смерти в level-room (не title room) не триггерит title_screen."""
    env = _make_env(
        death_mode=DEATH_MODE_GAME_OVER,
        start_lives=3,
        title_end_rooms=(0x00,),
        title_end_confirm_steps=3,
    )
    _confirm_death(env, 0, room=0x06)
    for _ in range(5):
        _obs, _r, terminated, _trunc, info = _step_with_lives(env, 0, room=0x06)
        assert terminated is False
        assert info.get("terminate_reason") is None


def test_title_screen_stops_after_confirm_streak() -> None:
    env = _make_env(
        death_mode=DEATH_MODE_GAME_OVER,
        start_lives=3,
        title_end_rooms=(0x00,),
        title_end_confirm_steps=3,
    )
    _confirm_death(env, 0, room=0x06)
    _step_with_lives(env, 2, room=0x06)
    for _ in range(2):
        _obs, _r, terminated, _trunc, info = _step_with_lives(env, 0, room=0x00)
        assert terminated is False
    _obs, _r, terminated, _trunc, info = _step_with_lives(env, 0, room=0x00)
    assert terminated is True
    assert info["terminate_reason"] == TERMINATE_REASON_TITLE


def _step_ram(env: BaseNesEnv, *, lives: int, room: int, x: int) -> tuple:
    bridge = env._bridge
    bridge.step.return_value = {
        "obs_file": "x",
        "format": "raw",
        "w": 84,
        "h": 84,
        "lives": lives,
        "room": room,
        "x": x,
        "y": 20,
    }
    bridge.decode_obs_from_response.return_value = np.zeros((84, 84), dtype=np.uint8)
    return env.step(0)


def test_title_pose_return_stops_after_leaving_pose() -> None:
    """После level-room (≥0x08) вернулись в room=0/x=129 → title_screen."""
    env = _make_env(
        death_mode=DEATH_MODE_GAME_OVER,
        start_lives=6,
        title_end_rooms=(0x00,),
        title_end_confirm_steps=99,
    )
    env.title_pose_x = 129
    env.title_pose_confirm_steps = 3
    _step_ram(env, lives=6, room=0x00, x=129)  # старт на позе
    _step_ram(env, lives=6, room=0x0B, x=8)  # level-room
    assert env._left_title_pose is True
    assert env._seen_level_room is True
    for i in range(3):
        _obs, _r, terminated, _trunc, info = _step_ram(env, lives=6, room=0x00, x=129)
        if i < 2:
            assert terminated is False
    assert terminated is True
    assert info["terminate_reason"] == TERMINATE_REASON_TITLE


def test_title_pose_ignores_start_corridor_without_level() -> None:
    """Коридор x=129 без level-room не стопит эпизод."""
    env = _make_env(death_mode=DEATH_MODE_GAME_OVER, start_lives=6, title_end_rooms=(0x00,))
    env.title_pose_x = 129
    env.title_pose_confirm_steps = 2
    _step_ram(env, lives=6, room=0x00, x=10)  # ушли с позы, но не level
    for _ in range(4):
        _obs, _r, terminated, _trunc, info = _step_ram(env, lives=6, room=0x00, x=129)
        assert terminated is False
        assert info.get("terminate_reason") is None


def test_title_pose_parses_hex_room_strings() -> None:
    """Bridge отдаёт room как '0x00' — поза title должна распознаваться."""
    env = _make_env(death_mode=DEATH_MODE_GAME_OVER, start_lives=6, title_end_rooms=(0x00,))
    env.title_pose_x = 129
    env.title_pose_confirm_steps = 2
    env._left_title_pose = True
    env._seen_level_room = True
    bridge = env._bridge
    for i in range(2):
        bridge.step.return_value = {
            "obs_file": "x",
            "format": "raw",
            "w": 84,
            "h": 84,
            "lives": 6,
            "room": "0x00",
            "x": 129,
            "y": 20,
        }
        bridge.decode_obs_from_response.return_value = np.zeros((84, 84), dtype=np.uint8)
        _obs, _r, terminated, _trunc, info = env.step(0)
    assert terminated is True
    assert info["terminate_reason"] == TERMINATE_REASON_TITLE


def test_lives_refill_after_death_stops_as_title() -> None:
    """После смерти refill до start_lives в title-room ⇒ soft-reset."""
    env = _make_env(
        death_mode=DEATH_MODE_GAME_OVER,
        start_lives=6,
        title_end_rooms=(0x00,),
    )
    _confirm_death(env, 5, room=0x0B)
    # refill в level-room — не title
    _obs, _r, terminated, _trunc, info = _step_with_lives(env, 6, room=0x04)
    assert terminated is False
    _obs, _r, terminated, _trunc, info = _step_with_lives(env, 6, room=0x00)
    assert terminated is True
    assert info["terminate_reason"] == TERMINATE_REASON_TITLE
    assert info["death_count"] == 1


def test_title_stop_requires_prior_death() -> None:
    """Без death_count title-сигнатура не завершает эпизод."""
    env = _make_env(
        death_mode=DEATH_MODE_GAME_OVER,
        start_lives=3,
        title_end_rooms=(0x00,),
        title_end_confirm_steps=2,
    )
    env._prev_lives = 0
    for _ in range(4):
        _obs, _r, terminated, _trunc, info = _step_with_lives(env, 0, room=0x00)
        assert info["died"] is False
        assert info["death_count"] == 0
        assert terminated is False


def test_game_over_budget_sets_terminate_reason_death() -> None:
    env = _make_env(death_mode=DEATH_MODE_GAME_OVER, start_lives=3, title_end_rooms=(0x00,))
    _confirm_death(env, 0, room=0x06)
    _step_with_lives(env, 2, room=0x06)
    _confirm_death(env, 0, room=0x06)
    _step_with_lives(env, 1, room=0x06)
    terminated, info = _confirm_death(env, 0, room=0x06)
    assert terminated is True
    assert info["terminate_reason"] == TERMINATE_REASON_DEATH
    assert info["death_count"] == 3
