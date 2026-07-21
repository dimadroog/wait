"""Базовая Gymnasium-среда NES через FCEUX bridge (игро-независимая)."""
from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any, Sequence

import gymnasium as gym
import numpy as np
import yaml

from fceux_bridge import FceuxBridge, FceuxBridgeError
from project_paths import mission_dir

OBS_SHAPE = (4, 84, 84)
DEFAULT_MAX_EPISODE_STEPS = 8_000

# life_lost: terminated на первую потерю жизни.
# game_over: died на каждую потерю; terminated после N потерь (N = lives на старте).
# Сырой lives==0 часто анимация смерти, не game over — считаем confirmed dips.
DEATH_MODE_LIFE_LOST = "life_lost"
DEATH_MODE_GAME_OVER = "game_over"
DEATH_MODES = frozenset({DEATH_MODE_LIFE_LOST, DEATH_MODE_GAME_OVER})

TERMINATE_REASON_DEATH = "death"
TERMINATE_REASON_TITLE = "title_screen"
TERMINATE_REASON_GAME_OVER = "game_over_screen"
DEFAULT_DEATH_CONFIRM_STEPS = 1


def parse_hex_or_int(value: Any) -> int:
    """Parse int or hex string ('0x00') from bridge/YAML."""
    if isinstance(value, int):
        return int(value)
    text = str(value).strip().lower()
    if text.startswith("0x"):
        return int(text, 16)
    return int(text, 0) if text else 0


def parse_int_set(values: Sequence[Any] | None) -> frozenset[int]:
    if not values:
        return frozenset()
    return frozenset(parse_hex_or_int(v) for v in values)


class BaseNesEnv(gym.Env):
    """reset/step через FceuxBridge; награды — в CheckpointRewardWrapper.

    Игро-специфичный конец эпизода (title/attract и т.п.) — через hooks
    в subclass плагина (`games/<game>/env/`), не через константы игры в ядре.
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        *,
        game_id: str,
        mission_id: str,
        action_strings: Sequence[str],
        lives_min: int = 0,
        lives_max: int = 9,
        save_state: str | None = None,
        frame_skip: int = 4,
        max_episode_steps: int = DEFAULT_MAX_EPISODE_STEPS,
        turbo: bool = True,
        session_id: str = "default",
        show_window: bool = False,
        fm2_template: str | Path | None = None,
        death_mode: str = DEATH_MODE_LIFE_LOST,
        death_confirm_steps: int = DEFAULT_DEATH_CONFIRM_STEPS,
    ) -> None:
        super().__init__()
        self.game_id = game_id
        self.mission_id = mission_id
        self.mission = mission_dir(game_id, mission_id)
        self.action_strings = tuple(action_strings)
        self.lives_min = lives_min
        self.lives_max = lives_max
        mode = str(death_mode or DEATH_MODE_LIFE_LOST).strip().lower()
        if mode not in DEATH_MODES:
            raise ValueError(f"death_mode must be one of {sorted(DEATH_MODES)}, got {death_mode!r}")
        self.death_mode = mode
        self.death_confirm_steps = max(1, int(death_confirm_steps))
        self.save_state = save_state or self._default_save_state()
        self.frame_skip = frame_skip
        self.max_episode_steps = max_episode_steps
        self.turbo = turbo
        self.session_id = session_id
        self.show_window = show_window
        self.fm2_template = Path(fm2_template) if fm2_template else None

        self.observation_space = gym.spaces.Box(0.0, 1.0, OBS_SHAPE, dtype=np.float32)
        self.action_space = gym.spaces.Discrete(len(self.action_strings))

        self._bridge: FceuxBridge | None = None
        self._frames: deque[np.ndarray] = deque(maxlen=4)
        self._step_count = 0
        self._episode_start_lives: int | None = None
        self._prev_lives: int | None = None
        self._death_count = 0
        self._pending_lives_from: int | None = None
        self._pending_death_streak = 0

    def _default_save_state(self) -> str:
        manifest = self.mission / "config" / "playthrough_manifest.yaml"
        if manifest.is_file():
            manifest = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
            segments = manifest.get("segments") or []
            if segments:
                return str(segments[0].get("save_state", "save_states/cp0.fc0"))
        return "save_states/cp0.fc0"

    def _action_string(self, action: int) -> str:
        return self.action_strings[int(action)]

    def _valid_lives(self, lives: int) -> bool:
        return self.lives_min <= lives <= self.lives_max

    def _ensure_bridge(self) -> FceuxBridge:
        if self._bridge is None:
            self._bridge = FceuxBridge(
                self.mission,
                self.game_id,
                frame_skip=self.frame_skip,
                session_id=self.session_id,
                show_window=self.show_window,
                fm2_template=self.fm2_template,
            )
        return self._bridge

    def _obs_stack(self) -> np.ndarray:
        if len(self._frames) < 4:
            frame = self._frames[-1] if self._frames else np.zeros((84, 84), dtype=np.uint8)
            while len(self._frames) < 4:
                self._frames.append(frame.copy())
        return np.stack(list(self._frames), axis=0).astype(np.float32) / 255.0

    def _push_obs(self, gray: np.ndarray) -> None:
        self._frames.append(gray.astype(np.uint8))

    def _clear_pending_death(self) -> None:
        self._pending_lives_from = None
        self._pending_death_streak = 0

    def _ram_int(self, ram: dict[str, Any], key: str, default: int = -1) -> int:
        try:
            return parse_hex_or_int(ram.get(key, default))
        except (TypeError, ValueError):
            return default

    def _death_occurred(self, ram: dict[str, Any]) -> bool:
        """True, если подтверждена потеря жизни (dip ≥ death_confirm_steps)."""
        lives = int(ram.get("lives", 0))
        if not self._valid_lives(lives):
            return False
        if self._episode_start_lives is None:
            self._episode_start_lives = lives
            self._prev_lives = lives
            return False

        if self._pending_lives_from is not None:
            if lives >= self._pending_lives_from:
                self._clear_pending_death()
                self._prev_lives = lives
                return False
            self._pending_death_streak += 1
            if self._pending_death_streak >= self.death_confirm_steps:
                self._clear_pending_death()
                self._prev_lives = lives
                return True
            return False

        if self._prev_lives is not None and lives < self._prev_lives:
            self._pending_lives_from = self._prev_lives
            self._pending_death_streak = 1
            if self._pending_death_streak >= self.death_confirm_steps:
                self._clear_pending_death()
                self._prev_lives = lives
                return True
            return False

        self._prev_lives = lives
        return False

    def _terminate_on_death(self, died: bool, ram: dict[str, Any]) -> bool:
        """Заканчивать ли эпизод при потере жизни."""
        if not died:
            return False
        if self.death_mode == DEATH_MODE_LIFE_LOST:
            return True
        self._death_count += 1
        budget = max(int(self._episode_start_lives or 1), 1)
        return self._death_count >= budget

    def _on_episode_reset(self) -> None:
        """Hook: сброс игро-специфичного состояния (плагин)."""

    def _on_ram(self, ram: dict[str, Any]) -> None:
        """Hook: каждый step после чтения RAM (плагин)."""

    def _secondary_terminate(self, ram: dict[str, Any]) -> bool:
        """Hook: доп. конец эпизода (title/attract и т.п.). Default: нет."""
        return False

    def _should_defer_truncate(self, ram: dict[str, Any]) -> bool:
        """Hook: отложить truncated на max_steps. Default: нет."""
        return False

    def _secondary_terminate_reason(self) -> str:
        return TERMINATE_REASON_TITLE

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        super().reset(seed=seed)
        opts = options or {}
        state = str(opts.get("save_state", self.save_state))

        bridge = self._ensure_bridge()
        bridge_response = bridge.reset_to_state(state)
        if not self.turbo:
            bridge.turbo(False)

        self._frames.clear()
        self._step_count = 0
        self._episode_start_lives = None
        self._prev_lives = None
        self._death_count = 0
        self._clear_pending_death()
        self._on_episode_reset()

        gray = bridge.decode_obs_from_response(bridge_response)
        self._push_obs(gray)

        ram = {
            k: bridge_response[k]
            for k in ("room", "x", "y", "hp", "lives", "checkpoint", "frame")
            if k in bridge_response
        }
        if not ram:
            ram = bridge.get_ram()
        lives = int(ram.get("lives", 0))
        if self._valid_lives(lives) and lives > self.lives_min:
            self._episode_start_lives = lives
            self._prev_lives = lives

        info = {
            "ram": ram,
            "died": False,
            "death_mode": self.death_mode,
            "mission_complete": False,
            "max_checkpoint": -1,
            "episode_frames": 0,
        }
        return self._obs_stack(), info

    def _soft_reset_after_bridge_error(
        self, error: FceuxBridgeError
    ) -> tuple[np.ndarray, dict[str, Any]]:
        """Восстановить env после IPC-сбоя; не пробрасывать в SubprocVecEnv worker."""
        try:
            bridge = self._ensure_bridge()
            bridge_response = bridge.reset_to_state(self.save_state)
        except FceuxBridgeError:
            if self._bridge is not None:
                try:
                    self._bridge._force_close_proc()
                except OSError:
                    pass
                self._bridge = None
            bridge = self._ensure_bridge()
            bridge_response = bridge.reset_to_state(self.save_state)

        self._frames.clear()
        self._step_count = 0
        self._episode_start_lives = None
        self._prev_lives = None
        self._death_count = 0
        self._clear_pending_death()
        self._on_episode_reset()

        gray = bridge.decode_obs_from_response(bridge_response)
        self._push_obs(gray)

        ram = {
            k: bridge_response[k]
            for k in ("room", "x", "y", "hp", "lives", "checkpoint", "frame")
            if k in bridge_response
        }
        if not ram:
            ram = bridge.get_ram()
        lives = int(ram.get("lives", 0))
        if self._valid_lives(lives) and lives > self.lives_min:
            self._episode_start_lives = lives
            self._prev_lives = lives

        info: dict[str, Any] = {
            "ram": ram,
            "died": False,
            "death_mode": self.death_mode,
            "mission_complete": False,
            "max_checkpoint": -1,
            "episode_frames": 0,
            "bridge_error": str(error),
            "bridge_recovered": True,
        }
        return self._obs_stack(), info

    def step(self, action: int) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        bridge = self._ensure_bridge()
        action_str = self._action_string(int(action))

        try:
            step_data = bridge.step(action_str)
        except FceuxBridgeError as exc:
            print(
                f"WARNING [base_nes_env] bridge step failed "
                f"session={self.session_id}: {exc}; soft reset"
            )
            obs, info = self._soft_reset_after_bridge_error(exc)
            info["action"] = action_str
            return obs, 0.0, False, True, info

        gray = bridge.decode_obs_from_response(step_data)
        self._push_obs(gray)

        ram = {
            k: step_data[k]
            for k in ("room", "x", "y", "hp", "lives", "checkpoint", "frame")
            if k in step_data
        }
        if not ram:
            ram = bridge.get_ram()

        died = self._death_occurred(ram)
        self._step_count += 1
        self._on_ram(ram)
        terminated_death = self._terminate_on_death(died, ram)
        terminated_secondary = False if terminated_death else self._secondary_terminate(ram)
        terminated = terminated_death or terminated_secondary
        truncated = self._step_count >= self.max_episode_steps
        if truncated and not terminated and self._should_defer_truncate(ram):
            truncated = False

        info: dict[str, Any] = {
            "ram": ram,
            "died": died,
            "death_mode": self.death_mode,
            "death_count": self._death_count,
            "mission_complete": False,
            "max_checkpoint": -1,
            "episode_frames": self._step_count,
            "action": action_str,
        }
        if terminated_death:
            info["terminate_reason"] = TERMINATE_REASON_DEATH
        elif terminated_secondary:
            info["terminate_reason"] = self._secondary_terminate_reason()
        return self._obs_stack(), 0.0, terminated, truncated, info

    def close(self) -> None:
        if self._bridge is not None:
            self._bridge.close()
            self._bridge = None
