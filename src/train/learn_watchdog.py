"""Watchdog learn(): abort при зависании SubprocVecEnv (FAIL_REPORT R2.3)."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback, CallbackList
from stable_baselines3.common.vec_env import VecEnv

DEFAULT_LEARN_STALL_TIMEOUT_S = 300.0
DEFAULT_SESSION_WALL_TIMEOUT_S = 3600.0


class LearnStallError(RuntimeError):
    """learn() остановлен watchdog — нет прогресса timesteps."""


class SessionWallTimeoutError(RuntimeError):
    """learn() остановлен по лимиту wall-clock сессии."""


@dataclass
class LearnWatchdogState:
    session_start_mono: float = field(default_factory=time.perf_counter)
    last_progress_mono: float = field(default_factory=time.perf_counter)
    last_timesteps: int = 0
    aborted: bool = False
    abort_reason: str | None = None
    abort_kind: str | None = None


def safe_close_vec_env(vec_env: VecEnv | None) -> None:
    if vec_env is None:
        return
    try:
        vec_env.close()
    except (EOFError, BrokenPipeError, OSError):
        pass


class LearnProgressCallback(BaseCallback):
    """Обновляет метку прогресса для watchdog."""

    def __init__(self, state: LearnWatchdogState, verbose: int = 0):
        super().__init__(verbose)
        self._state = state

    def _on_step(self) -> bool:
        timesteps = int(self.num_timesteps)
        if timesteps > self._state.last_timesteps:
            self._state.last_timesteps = timesteps
            self._state.last_progress_mono = time.perf_counter()
        return not self._state.aborted


def _watchdog_loop(
    state: LearnWatchdogState,
    vec_env: VecEnv,
    *,
    stall_timeout_s: float,
    wall_timeout_s: float,
    stop_event: threading.Event,
) -> None:
    while not stop_event.wait(1.0):
        if state.aborted:
            return
        now = time.perf_counter()
        if wall_timeout_s > 0:
            elapsed = now - state.session_start_mono
            if elapsed > wall_timeout_s:
                state.aborted = True
                state.abort_kind = "wall"
                state.abort_reason = (
                    f"session wall {elapsed:.0f}s > {wall_timeout_s:.0f}s"
                )
                print(f"WARNING [learn_watchdog] {state.abort_reason}; closing vec_env")
                safe_close_vec_env(vec_env)
                return
        if stall_timeout_s > 0:
            idle_s = now - state.last_progress_mono
            if idle_s > stall_timeout_s:
                state.aborted = True
                state.abort_kind = "stall"
                state.abort_reason = (
                    f"learn stall {idle_s:.0f}s > {stall_timeout_s:.0f}s "
                    "(no timesteps progress)"
                )
                print(f"WARNING [learn_watchdog] {state.abort_reason}; closing vec_env")
                safe_close_vec_env(vec_env)
                return


def learn_with_stall_watchdog(
    model: PPO,
    vec_env: VecEnv,
    *,
    stall_timeout_s: float,
    wall_timeout_s: float = 0.0,
    session_start_mono: float | None = None,
    callback: BaseCallback | CallbackList | None = None,
    **learn_kwargs: Any,
) -> None:
    """model.learn с фоновым watchdog; при stall/wall закрывает vec_env и бросает ошибку."""
    if stall_timeout_s <= 0 and wall_timeout_s <= 0:
        model.learn(callback=callback, **learn_kwargs)
        return

    state = LearnWatchdogState()
    if session_start_mono is not None:
        state.session_start_mono = session_start_mono
    progress_cb = LearnProgressCallback(state)
    merged: BaseCallback | CallbackList
    if callback is None:
        merged = progress_cb
    elif isinstance(callback, CallbackList):
        merged = CallbackList([progress_cb, *callback.callbacks])
    else:
        merged = CallbackList([progress_cb, callback])

    stop_event = threading.Event()
    watchdog = threading.Thread(
        target=_watchdog_loop,
        args=(state, vec_env),
        kwargs={
            "stall_timeout_s": stall_timeout_s,
            "wall_timeout_s": wall_timeout_s,
            "stop_event": stop_event,
        },
        daemon=True,
        name="learn-watchdog",
    )
    watchdog.start()
    learn_error: Exception | None = None
    try:
        model.learn(callback=merged, **learn_kwargs)
    except (EOFError, BrokenPipeError) as exc:
        learn_error = exc
    finally:
        stop_event.set()
        watchdog.join(timeout=2.0)

    if state.aborted:
        if state.abort_kind == "wall":
            raise SessionWallTimeoutError(state.abort_reason or "session wall timeout")
        raise LearnStallError(state.abort_reason or "learn stalled")
    if learn_error is not None:
        raise learn_error
