"""Unit: Rush'n Attack screen phase_id detector (TASK_POLICY_SEPARATION)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from env.loader import import_game_env

RushnAttackEnv = import_game_env("rushn_attack").RushnAttackEnv


def _make_env(
    *,
    screen_phases: dict | None = None,
    title_level_room_min: int | None = 0x08,
) -> RushnAttackEnv:
    if screen_phases is None:
        screen_phases = {
            "level_room_min": "0x08",
            "title": {"rooms": ["0x00"], "x": 129, "ys": [131, 133, 135]},
        }
    with patch("env.base_nes_env.mission_dir") as mission_dir:
        mission_dir.return_value = MagicMock()
        env = RushnAttackEnv(
            game_id="rushn_attack",
            mission_id="m1",
            action_strings=("noop", "start"),
            save_state="save_states/cp_gameplay0.fc0",

            session_id="test_phase",
            title_end_rooms=(0x00,),
            title_pose_x=129,
            title_pose_ys=(131, 133, 135),
            title_level_room_min=title_level_room_min,
            game_over_freeze_confirm_steps=0,
            screen_phases=screen_phases,
        )
    env._bridge = MagicMock()
    env._frames.append(np.zeros((84, 84), dtype=np.uint8))
    env._episode_start_lives = 6
    env._prev_lives = 6
    env._death_count = 0
    env._on_episode_reset()
    return env


def _step_ram(
    env: RushnAttackEnv,
    *,
    lives: int = 6,
    room: int = 0x00,
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


def _reset_ram(
    env: RushnAttackEnv,
    *,
    lives: int = 6,
    room: int = 0x0C,
    x: int = 40,
    y: int = 40,
):
    bridge = env._bridge
    bridge.reset_to_state.return_value = {
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
    bridge.get_ram.return_value = {
        "lives": lives,
        "room": room,
        "x": x,
        "y": y,
    }
    return env.reset()


def test_title_pose_is_title_phase() -> None:
    env = _make_env()
    _obs, _r, _t, _tr, info = _step_ram(env, room=0x00, x=129, y=133, lives=0)
    assert info["phase_id"] == "title"


def test_pre_level_non_title_is_intro() -> None:
    env = _make_env()
    # cutscene / переход: room 0, не title pose
    _obs, _r, _t, _tr, info = _step_ram(env, room=0x00, x=80, y=95, lives=6)
    assert info["phase_id"] == "intro"


def test_level_room_is_gameplay() -> None:
    env = _make_env()
    _obs, _r, _t, _tr, info = _step_ram(env, room=0x08, x=40, y=40)
    assert info["phase_id"] == "gameplay"


def test_sticky_gameplay_after_level_then_room0() -> None:
    env = _make_env()
    _step_ram(env, room=0x08, x=40, y=40)
    # коридор / late room 0x00 после уровня — не intro
    _obs, _r, _t, _tr, info = _step_ram(env, room=0x00, x=50, y=70)
    assert info["phase_id"] == "gameplay"


def test_reset_into_level_is_gameplay() -> None:
    env = _make_env()
    _obs, info = _reset_ram(env, room=0x0C, x=40, y=40)
    assert info["phase_id"] == "gameplay"


def test_reset_title_pose_is_title() -> None:
    env = _make_env()
    _obs, info = _reset_ram(env, room=0x00, x=129, y=131, lives=0)
    assert info["phase_id"] == "title"


def test_disabled_when_screen_phases_empty() -> None:
    env = _make_env(screen_phases={})
    assert env.screen_phases_enabled is False
    _obs, _r, _t, _tr, info = _step_ram(env, room=0x00, x=129, y=133)
    assert "phase_id" not in info
