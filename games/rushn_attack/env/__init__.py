"""Rush'n Attack — Gymnasium env (games/rushn_attack/env/)."""
from __future__ import annotations

from typing import Any, Sequence

import gymnasium as gym

from env.base_nes_env import (
    TERMINATE_REASON_TITLE,
    BaseNesEnv,
    parse_hex_or_int,
    parse_int_set,
)
from project_paths import game_dir, load_yaml, mission_dir
from rewards.checkpoint_wrapper import CheckpointRewardWrapper

_GAME_ID = "rushn_attack"


def _load_env_config() -> dict[str, Any]:
    return load_yaml(game_dir(_GAME_ID) / "env_config.yaml")


class RushnAttackEnv(BaseNesEnv):
    """RnA: secondary terminate на title/attract idle после попытки; не mid-flash."""

    def __init__(
        self,
        *,
        title_end_rooms: Sequence[Any] | None = None,
        title_end_confirm_steps: int = 8,
        title_pose_x: int | None = None,
        title_pose_ys: Sequence[Any] | None = None,
        title_pose_confirm_steps: int = 32,
        title_level_room_min: int | None = 0x08,
        title_min_attempt_steps: int = 120,
        title_pose_truncate_grace: int = 0,
        title_pose_truncate_cool: int = 0,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.title_end_rooms = parse_int_set(title_end_rooms)
        self.title_end_confirm_steps = max(1, int(title_end_confirm_steps))
        self.title_pose_x = None if title_pose_x is None else int(title_pose_x)
        self.title_pose_ys = frozenset(int(y) for y in (title_pose_ys or ()))
        self.title_pose_confirm_steps = max(1, int(title_pose_confirm_steps))
        self.title_level_room_min = (
            None if title_level_room_min is None else int(title_level_room_min)
        )
        self.title_min_attempt_steps = max(0, int(title_min_attempt_steps))
        self.title_pose_truncate_grace = max(0, int(title_pose_truncate_grace))
        self.title_pose_truncate_cool = max(0, int(title_pose_truncate_cool))
        self._on_episode_reset()

    def _on_episode_reset(self) -> None:
        self._seen_level_room = False
        self._title_end_streak = 0
        self._title_pose_streak = 0
        self._title_pose_trunc_cool = 0

    def _on_ram(self, ram: dict[str, Any]) -> None:
        if self.title_level_room_min is None:
            return
        room = self._ram_int(ram, "room")
        if room >= self.title_level_room_min:
            self._seen_level_room = True

    def _attempt_progressed(self) -> bool:
        """Попытка началась: min steps, level-room, или ≥1 death.

        Важно: gen0 часто остаётся в room=0x00 — гейт только по level_room
        отключал secondary и оставлял title/attract idle в FM2.
        """
        if self._death_count >= 1:
            return True
        if self._seen_level_room:
            return True
        return self._step_count >= self.title_min_attempt_steps

    def _title_pose_xy_match(self, ram: dict[str, Any]) -> bool:
        if self.title_pose_x is None or not self.title_pose_ys:
            return False
        lives = int(ram.get("lives", 0))
        if not self._valid_lives(lives) or lives < 1:
            return False
        x = self._ram_int(ram, "x")
        y = self._ram_int(ram, "y")
        return x == self.title_pose_x and y in self.title_pose_ys

    def _title_pose_coords_match(self, ram: dict[str, Any]) -> bool:
        if not self.title_end_rooms or not self._title_pose_xy_match(ram):
            return False
        return self._ram_int(ram, "room") in self.title_end_rooms

    def _title_screen_match(self, ram: dict[str, Any]) -> bool:
        """Title с lives<1 после попытки (не только после counted death)."""
        if not self.title_end_rooms or not self._attempt_progressed():
            return False
        lives = int(ram.get("lives", 0))
        if lives >= 1:
            return False
        return self._ram_int(ram, "room") in self.title_end_rooms

    def _attract_pose_match(self, ram: dict[str, Any]) -> bool:
        """Устойчивая attract/title standing @ L≥1 после level (не mid-flash)."""
        if not self._attempt_progressed():
            return False
        return self._title_pose_coords_match(ram)

    def _secondary_terminate(self, ram: dict[str, Any]) -> bool:
        if self._attract_pose_match(ram):
            self._title_pose_streak += 1
            if self._title_pose_streak >= self.title_pose_confirm_steps:
                return True
        else:
            self._title_pose_streak = 0

        if self._title_screen_match(ram):
            self._title_end_streak += 1
        else:
            self._title_end_streak = 0
        return self._title_end_streak >= self.title_end_confirm_steps

    def _should_defer_truncate(self, ram: dict[str, Any]) -> bool:
        if self.title_pose_truncate_grace <= 0:
            self._title_pose_trunc_cool = 0
            return False

        in_title = self._title_pose_coords_match(ram)
        if in_title:
            self._title_pose_trunc_cool = self.title_pose_truncate_cool
            pose_active = True
        elif self._title_pose_xy_match(ram) and self._title_pose_trunc_cool > 0:
            pose_active = True
            self._title_pose_trunc_cool -= 1
        else:
            self._title_pose_trunc_cool = 0
            pose_active = False

        if self._step_count < self.max_episode_steps:
            return False
        if self._step_count >= self.max_episode_steps + self.title_pose_truncate_grace:
            return False
        return pose_active

    def _secondary_terminate_reason(self) -> str:
        return TERMINATE_REASON_TITLE


def make_env(
    mission_id: str = "m1",
    *,
    wrap_rewards: bool = True,
    reward_profile: str = "default",
    reward_overrides: dict[str, Any] | None = None,
    game_id: str = _GAME_ID,
    **kwargs,
) -> gym.Env:
    """Фабрика Rush'n Attack: RushnAttackEnv + CheckpointRewardWrapper."""
    env_config = _load_env_config()
    actions = tuple(env_config.get("actions") or [])
    lives = env_config.get("lives") or {}
    if "death_mode" not in kwargs and env_config.get("death_mode"):
        kwargs["death_mode"] = str(env_config["death_mode"])
    if "death_confirm_steps" not in kwargs and env_config.get("death_confirm_steps") is not None:
        kwargs["death_confirm_steps"] = int(env_config["death_confirm_steps"])
    title_end = env_config.get("episode_end_title") or {}
    if "title_end_rooms" not in kwargs and title_end.get("rooms") is not None:
        kwargs["title_end_rooms"] = title_end.get("rooms")
    if "title_end_confirm_steps" not in kwargs and title_end.get("confirm_steps") is not None:
        kwargs["title_end_confirm_steps"] = int(title_end["confirm_steps"])
    if "title_pose_x" not in kwargs and title_end.get("title_x") is not None:
        kwargs["title_pose_x"] = int(title_end["title_x"])
    if "title_pose_ys" not in kwargs and title_end.get("title_ys") is not None:
        kwargs["title_pose_ys"] = title_end.get("title_ys")
    if "title_pose_confirm_steps" not in kwargs and title_end.get("pose_confirm_steps") is not None:
        kwargs["title_pose_confirm_steps"] = int(title_end["pose_confirm_steps"])
    if "title_pose_truncate_grace" not in kwargs and title_end.get("truncate_grace_steps") is not None:
        kwargs["title_pose_truncate_grace"] = int(title_end["truncate_grace_steps"])
    if "title_pose_truncate_cool" not in kwargs and title_end.get("truncate_cool_steps") is not None:
        kwargs["title_pose_truncate_cool"] = int(title_end["truncate_cool_steps"])
    if "title_level_room_min" not in kwargs and title_end.get("level_room_min") is not None:
        kwargs["title_level_room_min"] = parse_hex_or_int(title_end["level_room_min"])
    if "title_min_attempt_steps" not in kwargs and title_end.get("min_attempt_steps") is not None:
        kwargs["title_min_attempt_steps"] = int(title_end["min_attempt_steps"])
    env = RushnAttackEnv(
        game_id=game_id,
        mission_id=mission_id,
        action_strings=actions,
        lives_min=int(lives.get("min", 0)),
        lives_max=int(lives.get("max", 9)),
        **kwargs,
    )
    if wrap_rewards:
        routes = mission_dir(game_id, mission_id) / "config" / "routes.yaml"
        env = CheckpointRewardWrapper(
            env,
            routes,
            profile=reward_profile,
            reward_overrides=reward_overrides,
        )
    return env


__all__ = ["make_env", "RushnAttackEnv"]
