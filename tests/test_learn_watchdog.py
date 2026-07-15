"""Unit tests for learn stall watchdog (FAIL_REPORT R2.3)."""
from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest

from train.learn_watchdog import (
    LearnProgressCallback,
    LearnStallError,
    LearnWatchdogState,
    SessionWallTimeoutError,
    _watchdog_loop,
    learn_with_stall_watchdog,
)


def test_watchdog_loop_aborts_on_stall() -> None:
    state = LearnWatchdogState()
    state.last_progress_mono = 1000.0
    vec_env = MagicMock()
    stop = threading.Event()

    with patch("train.learn_watchdog.time.perf_counter", return_value=1400.0):
        _watchdog_loop(
            state,
            vec_env,
            stall_timeout_s=300.0,
            wall_timeout_s=0.0,
            stop_event=stop,
        )

    assert state.aborted is True
    assert state.abort_kind == "stall"
    assert state.abort_reason is not None
    vec_env.close.assert_called_once()


def test_watchdog_loop_aborts_on_session_wall() -> None:
    state = LearnWatchdogState(session_start_mono=1000.0)
    state.last_progress_mono = 1000.0
    vec_env = MagicMock()
    stop = threading.Event()

    with patch("train.learn_watchdog.time.perf_counter", return_value=4700.0):
        _watchdog_loop(
            state,
            vec_env,
            stall_timeout_s=0.0,
            wall_timeout_s=3600.0,
            stop_event=stop,
        )

    assert state.aborted is True
    assert state.abort_kind == "wall"
    assert "session wall" in (state.abort_reason or "")
    vec_env.close.assert_called_once()


def test_learn_with_stall_watchdog_raises_on_abort() -> None:
    model = MagicMock()
    vec_env = MagicMock()

    def fake_learn(*, callback=None, **kwargs):
        callbacks = callback.callbacks if isinstance(callback, CallbackList) else [callback]
        for cb in callbacks:
            if isinstance(cb, LearnProgressCallback):
                cb._state.aborted = True
                cb._state.abort_reason = "learn stall 301s > 300s (no timesteps progress)"
                return

    from stable_baselines3.common.callbacks import CallbackList

    model.learn.side_effect = fake_learn

    with patch("train.learn_watchdog.threading.Thread") as thread_cls:
        thread_cls.return_value = MagicMock()
        with pytest.raises(LearnStallError, match="learn stall"):
            learn_with_stall_watchdog(
                model,
                vec_env,
                stall_timeout_s=300.0,
                total_timesteps=128,
            )


def test_learn_with_stall_watchdog_raises_on_wall_timeout() -> None:
    model = MagicMock()
    vec_env = MagicMock()

    def fake_learn(*, callback=None, **kwargs):
        callbacks = callback.callbacks if isinstance(callback, CallbackList) else [callback]
        for cb in callbacks:
            if isinstance(cb, LearnProgressCallback):
                cb._state.aborted = True
                cb._state.abort_kind = "wall"
                cb._state.abort_reason = "session wall 3601s > 3600s"
                return

    from stable_baselines3.common.callbacks import CallbackList

    model.learn.side_effect = fake_learn

    with patch("train.learn_watchdog.threading.Thread") as thread_cls:
        thread_cls.return_value = MagicMock()
        with pytest.raises(SessionWallTimeoutError, match="session wall"):
            learn_with_stall_watchdog(
                model,
                vec_env,
                stall_timeout_s=0.0,
                wall_timeout_s=3600.0,
                total_timesteps=128,
            )
