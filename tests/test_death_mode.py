"""Unit tests for BaseNesEnv death_mode + RushnAttackEnv title/attract end."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from env.base_nes_env import (
    DEATH_MODE_GAME_OVER,
    DEATH_MODE_LIFE_LOST,
    TERMINATE_REASON_DEATH,
    TERMINATE_REASON_GAME_OVER,
    TERMINATE_REASON_TITLE,
    BaseNesEnv,
)
from env.loader import import_game_env

RushnAttackEnv = import_game_env("rushn_attack").RushnAttackEnv


def _make_base(
    *,
    death_mode: str = DEATH_MODE_LIFE_LOST,
    start_lives: int = 3,
    death_confirm_steps: int = 1,
    max_episode_steps: int = 8000,
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
            max_episode_steps=max_episode_steps,
        )
    env._bridge = MagicMock()
    env._frames.append(np.zeros((84, 84), dtype=np.uint8))
    env._episode_start_lives = start_lives
    env._prev_lives = start_lives
    env._death_count = 0
    env._pending_lives_from = None
    env._pending_death_streak = 0
    return env


def _make_rna(
    *,
    death_mode: str = DEATH_MODE_GAME_OVER,
    start_lives: int = 3,
    death_confirm_steps: int = 1,
    title_end_rooms: tuple[int, ...] | None = (0x00,),
    title_end_confirm_steps: int = 8,
    title_pose_x: int | None = None,
    title_pose_ys: tuple[int, ...] | None = None,
    title_pose_confirm_steps: int = 32,
    title_level_room_min: int | None = 0x08,
    title_min_attempt_steps: int = 120,
    title_pose_truncate_grace: int = 40,
    title_pose_truncate_cool: int = 16,
    game_over_freeze_confirm_steps: int = 0,
    max_episode_steps: int = 8000,
) -> RushnAttackEnv:
    with patch("env.base_nes_env.mission_dir") as mission_dir:
        mission_dir.return_value = MagicMock()
        env = RushnAttackEnv(
            game_id="rushn_attack",
            mission_id="m1",
            action_strings=("noop", "right"),
            save_state="save_states/cp0.fc0",
            session_id="test_death",
            death_mode=death_mode,
            death_confirm_steps=death_confirm_steps,
            title_end_rooms=title_end_rooms,
            title_end_confirm_steps=title_end_confirm_steps,
            title_pose_x=title_pose_x,
            title_pose_ys=title_pose_ys,
            title_pose_confirm_steps=title_pose_confirm_steps,
            title_level_room_min=title_level_room_min,
            title_min_attempt_steps=title_min_attempt_steps,
            title_pose_truncate_grace=title_pose_truncate_grace,
            title_pose_truncate_cool=title_pose_truncate_cool,
            game_over_freeze_confirm_steps=game_over_freeze_confirm_steps,
            max_episode_steps=max_episode_steps,
        )
    env._bridge = MagicMock()
    env._frames.append(np.zeros((84, 84), dtype=np.uint8))
    env._episode_start_lives = start_lives
    env._prev_lives = start_lives
    env._death_count = 0
    env._pending_lives_from = None
    env._pending_death_streak = 0
    env._on_episode_reset()
    return env


def _step_ram(
    env: BaseNesEnv,
    *,
    lives: int,
    room: int | str = 0x06,
    x: int = 10,
    y: int = 20,
):
    bridge = env._bridge
    bridge.step.return_value = {
        "obs_file": "x",
        "format": "raw",
        "w": 84,
        "h": 84,
        "lives": lives,
        "room": room,
        "x": x,
        "y": y,
    }
    bridge.decode_obs_from_response.return_value = np.zeros((84, 84), dtype=np.uint8)
    return env.step(0)


def _step_with_lives(env: BaseNesEnv, lives: int, *, room: int | str = 0x06):
    return _step_ram(env, lives=lives, room=room)


def test_invalid_death_mode_raises() -> None:
    with pytest.raises(ValueError, match="death_mode"):
        _make_base(death_mode="nope")


def test_life_lost_terminates_on_first_death() -> None:
    env = _make_base(death_mode=DEATH_MODE_LIFE_LOST, start_lives=3)
    _obs, _r, terminated, _trunc, info = _step_with_lives(env, 0)
    assert info["died"] is True
    assert terminated is True
    assert info["death_mode"] == DEATH_MODE_LIFE_LOST


def test_game_over_continues_when_lives_hit_zero_transient() -> None:
    env = _make_base(death_mode=DEATH_MODE_GAME_OVER, start_lives=3)
    _obs, _r, terminated, _trunc, info = _step_with_lives(env, 0)
    assert info["died"] is True
    assert info["death_count"] == 1
    assert terminated is False


def test_game_over_terminates_after_budget_deaths() -> None:
    env = _make_base(death_mode=DEATH_MODE_GAME_OVER, start_lives=3)
    _step_with_lives(env, 0)
    _step_with_lives(env, 2)
    _step_with_lives(env, 0)
    _step_with_lives(env, 1)
    _obs, _r, terminated, _trunc, info = _step_with_lives(env, 0)
    assert info["died"] is True
    assert info["death_count"] == 3
    assert terminated is True


def test_no_death_when_lives_stable() -> None:
    env = _make_base(death_mode=DEATH_MODE_GAME_OVER, start_lives=3)
    _obs, _r, terminated, _trunc, info = _step_with_lives(env, 3)
    assert info["died"] is False
    assert terminated is False
    assert info["death_count"] == 0


def test_level_death_lives_zero_does_not_title_stop() -> None:
    env = _make_rna(
        death_mode=DEATH_MODE_GAME_OVER,
        start_lives=3,
        title_end_rooms=(0x00,),
        title_end_confirm_steps=3,
    )
    _step_with_lives(env, 0, room=0x06)
    for _ in range(5):
        _obs, _r, terminated, _trunc, info = _step_with_lives(env, 0, room=0x06)
        assert terminated is False
        assert info.get("terminate_reason") is None


def test_title_screen_stops_after_confirm_streak() -> None:
    env = _make_rna(
        death_mode=DEATH_MODE_GAME_OVER,
        start_lives=3,
        title_end_rooms=(0x00,),
        title_end_confirm_steps=3,
    )
    _step_with_lives(env, 0, room=0x06)
    _step_with_lives(env, 2, room=0x06)
    for _ in range(2):
        _obs, _r, terminated, _trunc, info = _step_with_lives(env, 0, room=0x00)
        assert terminated is False
    _obs, _r, terminated, _trunc, info = _step_with_lives(env, 0, room=0x00)
    assert terminated is True
    assert info["terminate_reason"] == TERMINATE_REASON_TITLE


def test_title_stop_after_level_without_death_count() -> None:
    """Soft-reset/game over title L=0 после level — стоп без counted death."""
    env = _make_rna(
        death_mode=DEATH_MODE_GAME_OVER,
        start_lives=6,
        title_end_rooms=(0x00,),
        title_end_confirm_steps=2,
    )
    _step_ram(env, lives=6, room=0x08, x=40, y=40)
    env._prev_lives = 0
    _step_ram(env, lives=0, room=0x00, x=129, y=133)
    _obs, _r, terminated, _trunc, info = _step_ram(env, lives=0, room=0x00, x=129, y=133)
    assert terminated is True
    assert info["terminate_reason"] == TERMINATE_REASON_TITLE
    assert info["death_count"] == 0


def test_title_stop_requires_prior_progress() -> None:
    """Без progress title L=0 не стопит (старт)."""
    env = _make_rna(
        death_mode=DEATH_MODE_GAME_OVER,
        start_lives=3,
        title_end_rooms=(0x00,),
        title_end_confirm_steps=2,
        title_min_attempt_steps=10_000,
        title_level_room_min=0x08,
    )
    env._prev_lives = 0
    for _ in range(4):
        _obs, _r, terminated, _trunc, info = _step_with_lives(env, 0, room=0x00)
        assert info["died"] is False
        assert info["death_count"] == 0
        assert terminated is False


def test_game_over_budget_sets_terminate_reason_death() -> None:
    env = _make_base(death_mode=DEATH_MODE_GAME_OVER, start_lives=3)
    _step_with_lives(env, 0, room=0x06)
    _step_with_lives(env, 2, room=0x06)
    _step_with_lives(env, 0, room=0x06)
    _step_with_lives(env, 1, room=0x06)
    _obs, _r, terminated, _trunc, info = _step_with_lives(env, 0, room=0x06)
    assert terminated is True
    assert info["terminate_reason"] == TERMINATE_REASON_DEATH
    assert info["death_count"] == 3


def test_lives_flicker_not_counted_as_death() -> None:
    env = _make_base(
        death_mode=DEATH_MODE_GAME_OVER,
        start_lives=6,
        death_confirm_steps=4,
    )
    _obs, _r, terminated, _trunc, info = _step_with_lives(env, 5)
    assert info["died"] is False
    assert terminated is False
    assert info["death_count"] == 0
    _obs, _r, terminated, _trunc, info = _step_with_lives(env, 6)
    assert info["died"] is False
    assert info["death_count"] == 0


def test_confirmed_death_requires_streak() -> None:
    env = _make_base(
        death_mode=DEATH_MODE_GAME_OVER,
        start_lives=6,
        death_confirm_steps=4,
    )
    for _ in range(3):
        _obs, _r, terminated, _trunc, info = _step_with_lives(env, 5)
        assert info["died"] is False
        assert info["death_count"] == 0
        assert terminated is False
    _obs, _r, terminated, _trunc, info = _step_with_lives(env, 5)
    assert info["died"] is True
    assert info["death_count"] == 1
    assert terminated is False


def test_title_stop_accepts_hex_room_string() -> None:
    env = _make_rna(
        death_mode=DEATH_MODE_GAME_OVER,
        start_lives=3,
        title_end_rooms=(0x00,),
        title_end_confirm_steps=2,
    )
    _step_with_lives(env, 0, room=0x06)
    _step_with_lives(env, 2, room=0x06)
    _step_with_lives(env, 0, room="0x00")
    _obs, _r, terminated, _trunc, info = _step_with_lives(env, 0, room="0x00")
    assert terminated is True
    assert info["terminate_reason"] == TERMINATE_REASON_TITLE


def _pose_env(*, confirm: int = 32) -> RushnAttackEnv:
    return _make_rna(
        death_mode=DEATH_MODE_GAME_OVER,
        start_lives=6,
        death_confirm_steps=4,
        title_end_rooms=(0x00,),
        title_end_confirm_steps=8,
        title_pose_x=129,
        title_pose_ys=(131, 133, 135),
        title_pose_confirm_steps=confirm,
        title_level_room_min=0x08,
    )


def test_corridor_pose_x129_y59_does_not_title_stop() -> None:
    env = _pose_env(confirm=5)
    _step_ram(env, lives=6, room=0x08, x=40, y=40)
    for _ in range(10):
        _obs, _r, terminated, _trunc, info = _step_ram(
            env, lives=6, room=0x00, x=129, y=59
        )
        assert terminated is False
        assert info.get("terminate_reason") is None


def test_attract_pose_before_attempt_progress_does_not_stop() -> None:
    env = _make_rna(
        death_mode=DEATH_MODE_GAME_OVER,
        start_lives=6,
        title_end_rooms=(0x00,),
        title_pose_x=129,
        title_pose_ys=(133,),
        title_pose_confirm_steps=5,
        title_level_room_min=0x08,
        title_min_attempt_steps=10_000,
    )
    for _ in range(10):
        _obs, _r, terminated, _trunc, info = _step_ram(
            env, lives=6, room=0x00, x=129, y=133
        )
        assert terminated is False
        assert info["death_count"] == 0


def test_attract_pose_after_min_steps_stops_without_level() -> None:
    """gen0 в room=0: secondary должен сработать после min_attempt_steps."""
    env = _make_rna(
        death_mode=DEATH_MODE_GAME_OVER,
        start_lives=6,
        title_end_rooms=(0x00,),
        title_pose_x=129,
        title_pose_ys=(133,),
        title_pose_confirm_steps=3,
        title_level_room_min=0x08,
        title_min_attempt_steps=5,
    )
    for _ in range(4):
        _step_ram(env, lives=6, room=0x00, x=10, y=59)
    for _ in range(2):
        _obs, _r, terminated, _trunc, info = _step_ram(
            env, lives=6, room=0x00, x=129, y=133
        )
        assert terminated is False
    _obs, _r, terminated, _trunc, info = _step_ram(
        env, lives=6, room=0x00, x=129, y=133
    )
    assert terminated is True
    assert info["terminate_reason"] == TERMINATE_REASON_TITLE


def test_attract_pose_flash_below_confirm_does_not_stop() -> None:
    env = _pose_env(confirm=32)
    _step_ram(env, lives=6, room=0x08, x=40, y=40)
    for _ in range(28):
        _obs, _r, terminated, _trunc, info = _step_ram(
            env, lives=6, room=0x00, x=129, y=133
        )
        assert terminated is False
    _obs, _r, terminated, _trunc, info = _step_ram(
        env, lives=6, room=0x00, x=129, y=59
    )
    assert terminated is False


def test_attract_pose_confirmed_stops_with_lives() -> None:
    """Idle attract standing после level → title terminate (режет хвост после game over/soft-reset)."""
    env = _pose_env(confirm=5)
    _step_ram(env, lives=6, room=0x08, x=40, y=40)
    for _ in range(4):
        _obs, _r, terminated, _trunc, info = _step_ram(
            env, lives=6, room=0x00, x=129, y=133
        )
        assert terminated is False
    _obs, _r, terminated, _trunc, info = _step_ram(
        env, lives=6, room=0x00, x=129, y=133
    )
    assert terminated is True
    assert info["terminate_reason"] == TERMINATE_REASON_TITLE
    assert info["death_count"] == 0


def test_truncate_deferred_during_title_pose_flash() -> None:
    env = _make_rna(
        death_mode=DEATH_MODE_GAME_OVER,
        start_lives=6,
        title_end_rooms=(0x00,),
        title_pose_x=129,
        title_pose_ys=(131, 133, 135),
        title_pose_confirm_steps=45,
        title_pose_truncate_grace=40,
        title_pose_truncate_cool=3,
        max_episode_steps=5,
    )
    for _ in range(5):
        _obs, _r, term, trunc, info = _step_ram(
            env, lives=6, room=0x00, x=129, y=133
        )
        assert term is False
        assert trunc is False
    _obs, _r, term, trunc, info = _step_ram(env, lives=6, room=0x00, x=129, y=133)
    assert trunc is False
    for _ in range(3):
        _obs, _r, term, trunc, info = _step_ram(env, lives=6, room=0x03, x=129, y=131)
        assert trunc is False
    _obs, _r, term, trunc, info = _step_ram(env, lives=6, room=0x03, x=129, y=131)
    assert term is False
    assert trunc is True


def test_truncate_force_after_grace_even_in_pose() -> None:
    env = _make_rna(
        death_mode=DEATH_MODE_GAME_OVER,
        start_lives=6,
        title_end_rooms=(0x00,),
        title_pose_x=129,
        title_pose_ys=(133,),
        title_pose_confirm_steps=999,
        title_pose_truncate_grace=2,
        title_pose_truncate_cool=16,
        max_episode_steps=3,
    )
    for _ in range(3):
        _step_ram(env, lives=6, room=0x00, x=129, y=133)
    _obs, _r, term, trunc, _info = _step_ram(env, lives=6, room=0x00, x=129, y=133)
    assert trunc is False
    _obs, _r, term, trunc, _info = _step_ram(env, lives=6, room=0x00, x=129, y=133)
    assert trunc is True


def test_truncate_not_deferred_on_level_death_pose() -> None:
    env = _make_rna(
        death_mode=DEATH_MODE_GAME_OVER,
        start_lives=6,
        title_end_rooms=(0x00,),
        title_pose_x=129,
        title_pose_ys=(131, 133, 135),
        title_pose_truncate_grace=40,
        title_pose_truncate_cool=16,
        max_episode_steps=3,
    )
    for _ in range(2):
        _step_ram(env, lives=6, room=0x0B, x=40, y=40)
    _obs, _r, term, trunc, info = _step_ram(env, lives=5, room=0x0B, x=129, y=131)
    assert trunc is True
    assert info["episode_frames"] == 3


def _game_over_freeze_env(*, confirm: int = 32) -> RushnAttackEnv:
    return _make_rna(
        death_mode=DEATH_MODE_GAME_OVER,
        start_lives=6,
        death_confirm_steps=4,
        title_end_rooms=(0x00,),
        title_end_confirm_steps=99,
        title_pose_x=129,
        title_pose_ys=(131, 133, 135),
        title_pose_confirm_steps=99,
        title_level_room_min=0x08,
        title_min_attempt_steps=120,
        game_over_freeze_confirm_steps=confirm,
    )


def test_game_over_freeze_below_confirm_does_not_stop() -> None:
    env = _game_over_freeze_env(confirm=32)
    _step_ram(env, lives=6, room=0x08, x=40, y=40)
    for _ in range(31):
        _obs, _r, terminated, _trunc, info = _step_ram(
            env, lives=6, room=0x00, x=129, y=95
        )
        assert terminated is False
        assert info.get("terminate_reason") is None


def test_game_over_freeze_confirmed_stops_y95() -> None:
    env = _game_over_freeze_env(confirm=32)
    _step_ram(env, lives=6, room=0x08, x=40, y=40)
    for _ in range(31):
        _step_ram(env, lives=6, room=0x00, x=129, y=95)
    _obs, _r, terminated, _trunc, info = _step_ram(
        env, lives=6, room=0x00, x=129, y=95
    )
    assert terminated is True
    assert info["terminate_reason"] == TERMINATE_REASON_GAME_OVER
    assert info["death_count"] == 0


def test_game_over_freeze_confirmed_stops_y41() -> None:
    """y на game over не фиксирован (эталон another_place / game_over_to_attract3)."""
    env = _game_over_freeze_env(confirm=5)
    _step_ram(env, lives=6, room=0x08, x=40, y=40)
    for _ in range(4):
        _step_ram(env, lives=6, room=0x00, x=129, y=41)
    _obs, _r, terminated, _trunc, info = _step_ram(
        env, lives=6, room=0x00, x=129, y=41
    )
    assert terminated is True
    assert info["terminate_reason"] == TERMINATE_REASON_GAME_OVER


def test_game_over_freeze_y_change_resets_streak() -> None:
    env = _game_over_freeze_env(confirm=5)
    _step_ram(env, lives=6, room=0x08, x=40, y=40)
    for _ in range(4):
        _step_ram(env, lives=6, room=0x00, x=129, y=95)
    for _ in range(4):
        _obs, _r, terminated, _trunc, info = _step_ram(
            env, lives=6, room=0x00, x=129, y=41
        )
        assert terminated is False
    _obs, _r, terminated, _trunc, info = _step_ram(
        env, lives=6, room=0x00, x=129, y=41
    )
    assert terminated is True
    assert info["terminate_reason"] == TERMINATE_REASON_GAME_OVER


def test_game_over_freeze_title_ys_not_match() -> None:
    """title standing идёт по attract-пути, не game_over_screen."""
    env = _make_rna(
        death_mode=DEATH_MODE_GAME_OVER,
        start_lives=6,
        title_end_rooms=(0x00,),
        title_pose_x=129,
        title_pose_ys=(133,),
        title_pose_confirm_steps=3,
        title_level_room_min=0x08,
        game_over_freeze_confirm_steps=3,
    )
    _step_ram(env, lives=6, room=0x08, x=40, y=40)
    for _ in range(2):
        _step_ram(env, lives=6, room=0x00, x=129, y=133)
    _obs, _r, terminated, _trunc, info = _step_ram(
        env, lives=6, room=0x00, x=129, y=133
    )
    assert terminated is True
    assert info["terminate_reason"] == TERMINATE_REASON_TITLE
