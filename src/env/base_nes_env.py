"""Базовая Gymnasium-среда NES через FCEUX bridge (игро-независимая)."""
from __future__ import annotations

from collections import deque
from typing import Any, Sequence

import gymnasium as gym
import numpy as np
import yaml

from fceux_bridge import FceuxBridge
from project_paths import mission_dir

OBS_SHAPE = (4, 84, 84)
DEFAULT_MAX_EPISODE_STEPS = 8_000


class BaseNesEnv(gym.Env):
    """reset/step через FceuxBridge; награды — в CheckpointRewardWrapper."""

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
    ) -> None:
        super().__init__()
        self.game_id = game_id
        self.mission_id = mission_id
        self.mission = mission_dir(game_id, mission_id)
        self.action_strings = tuple(action_strings)
        self.lives_min = lives_min
        self.lives_max = lives_max
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

    def _default_save_state(self) -> str:
        manifest = self.mission / "config" / "playthrough_manifest.yaml"
        if manifest.is_file():
            manifest = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
            segments = manifest.get("segments") or []
            if segments:
                return str(segments[0].get("save_state", "states/cp0.fc0"))
        return "states/cp0.fc0"

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

    def _death_occurred(self, ram: dict[str, Any]) -> bool:
        lives = int(ram.get("lives", 0))
        if not self._valid_lives(lives):
            return False
        if self._episode_start_lives is None:
            self._episode_start_lives = lives
            self._prev_lives = lives
            return False
        if self._prev_lives is not None and lives < self._prev_lives:
            return True
        return False

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
            # bridge.lua стартует в nothrottle; TURBO on после reset избыточен и гоняет IPC
            bridge.turbo(False)

        self._frames.clear()
        self._step_count = 0
        self._episode_start_lives = None
        self._prev_lives = None

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
        if self._valid_lives(lives):
            self._episode_start_lives = lives
            self._prev_lives = lives

        info = {
            "ram": ram,
            "died": False,
            "mission_complete": False,
            "max_checkpoint": -1,
            "episode_frames": 0,
        }
        return self._obs_stack(), info

    def step(self, action: int) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        bridge = self._ensure_bridge()
        action_str = self._action_string(int(action))

        step_data = bridge.step(action_str)
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
        terminated = bool(died)
        truncated = self._step_count >= self.max_episode_steps
        self._prev_lives = int(ram.get("lives", 0))

        info: dict[str, Any] = {
            "ram": ram,
            "died": died,
            "mission_complete": False,
            "max_checkpoint": -1,
            "episode_frames": self._step_count,
            "action": action_str,
        }
        return self._obs_stack(), 0.0, terminated, truncated, info

    def close(self) -> None:
        if self._bridge is not None:
            self._bridge.close()
            self._bridge = None
