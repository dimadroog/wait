"""Unit tests for BaseNesEnv bridge error recovery (FAIL_REPORT R2.1)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from env.base_nes_env import BaseNesEnv
from fceux_bridge import FceuxBridgeError


def _make_env() -> BaseNesEnv:
    with patch("env.base_nes_env.mission_dir") as mission_dir:
        mission_dir.return_value = MagicMock()
        env = BaseNesEnv(
            game_id="rushn_attack",
            mission_id="m1",
            action_strings=("noop", "right"),
            save_state="states/cp0.fc0",
            session_id="train_0",
        )
    env._bridge = MagicMock()
    env._frames.append(np.zeros((84, 84), dtype=np.uint8))
    return env


def test_step_soft_reset_on_bridge_error() -> None:
    env = _make_env()
    bridge = env._bridge
    bridge.step.side_effect = FceuxBridgeError("IPC timeout for STEP (45.0s) seq=3")
    bridge.reset_to_state.return_value = {
        "obs_file": "x",
        "format": "raw",
        "w": 84,
        "h": 84,
        "lives": 3,
    }
    bridge.decode_obs_from_response.return_value = np.zeros((84, 84), dtype=np.uint8)

    obs, reward, terminated, truncated, info = env.step(1)

    assert reward == 0.0
    assert terminated is False
    assert truncated is True
    assert info["bridge_recovered"] is True
    assert "IPC timeout" in info["bridge_error"]
    assert obs.shape == (4, 84, 84)
    bridge.reset_to_state.assert_called_once_with("states/cp0.fc0")


def test_step_reraises_non_bridge_errors() -> None:
    env = _make_env()
    env._bridge.step.side_effect = RuntimeError("unexpected")

    with pytest.raises(RuntimeError, match="unexpected"):
        env.step(0)
