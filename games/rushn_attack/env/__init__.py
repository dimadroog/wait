"""Rush'n Attack — Gymnasium env (games/rushn_attack/env/)."""
from __future__ import annotations

from typing import Any

import gymnasium as gym

from env.base_nes_env import BaseNesEnv
from project_paths import game_dir, load_yaml, mission_dir
from rewards.checkpoint_wrapper import CheckpointRewardWrapper

_GAME_ID = "rushn_attack"


def _load_env_config() -> dict[str, Any]:
    return load_yaml(game_dir(_GAME_ID) / "env_config.yaml")


def make_env(
    mission_id: str = "m1",
    *,
    wrap_rewards: bool = True,
    reward_profile: str = "default",
    reward_overrides: dict[str, Any] | None = None,
    game_id: str = _GAME_ID,
    **kwargs,
) -> gym.Env:
    """Фабрика Rush'n Attack: BaseNesEnv + CheckpointRewardWrapper."""
    env_config = _load_env_config()
    actions = tuple(env_config.get("actions") or [])
    lives = cfg.get("lives") or {}
    env = BaseNesEnv(
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


# Алиас для game.yaml → env_class
RushnAttackEnv = BaseNesEnv

__all__ = ["make_env", "RushnAttackEnv"]
