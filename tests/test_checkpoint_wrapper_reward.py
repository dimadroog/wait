"""Награда CheckpointRewardWrapper: один бонус на CP, без двойной выплаты id=1."""
from __future__ import annotations

from pathlib import Path

import gymnasium as gym
import numpy as np
import yaml

from rewards.checkpoint_wrapper import CheckpointRewardWrapper


class _RamStepEnv(gym.Env):
    """Минимальная среда: info['ram'] задаётся снаружи."""

    metadata = {"render_modes": []}

    def __init__(self) -> None:
        super().__init__()
        self.observation_space = gym.spaces.Box(low=0, high=1, shape=(1,), dtype=np.float32)
        self.action_space = gym.spaces.Discrete(1)
        self._ram: dict = {"room": "0x00", "stage": 0}
        self._died = False

    def set_ram(self, ram: dict) -> None:
        self._ram = dict(ram)

    def set_died(self, died: bool) -> None:
        self._died = died

    def reset(self, *, seed=None, options=None):
        return np.zeros(1, dtype=np.float32), {"ram": dict(self._ram)}

    def step(self, action):
        return (
            np.zeros(1, dtype=np.float32),
            0.0,
            False,
            False,
            {"ram": dict(self._ram), "died": self._died},
        )


def _wrapper(tmp_path: Path) -> tuple[CheckpointRewardWrapper, _RamStepEnv]:
    mission = tmp_path / "m1"
    cfg = mission / "config"
    cfg.mkdir(parents=True)
    routes = cfg / "routes.yaml"
    routes.write_text(
        yaml.dump(
            {
                "checkpoints": [
                    {"id": 1, "name": "cp1", "trigger": {"room": "0x00", "min_stage": 1}},
                    {"id": 2, "name": "cp2", "trigger": {"room": "0x00", "min_stage": 3}},
                ],
                "rewards": {"default": {"checkpoint_bonus": 100, "step_penalty": 0.0}},
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    inner = _RamStepEnv()
    wrapped = CheckpointRewardWrapper(inner, routes)
    return wrapped, inner


def test_first_cp_id_one_pays_single_bonus(tmp_path: Path) -> None:
    env, inner = _wrapper(tmp_path)
    env.reset()
    inner.set_ram({"room": "0x00", "stage": 1})
    _, reward, *_ = env.step(0)
    assert reward == 100.0
    assert env.best_checkpoint == 1
    assert env._paid_checkpoints == {1}


def test_stage_zero_on_reset_does_not_pay_cp(tmp_path: Path) -> None:
    env, inner = _wrapper(tmp_path)
    env.reset()
    inner.set_ram({"room": "0x00", "stage": 0})
    _, reward, *_ = env.step(0)
    assert reward == 0.0
    assert env.best_checkpoint == -1
    assert env._paid_checkpoints == set()


def test_two_cps_pay_two_bonuses_not_three(tmp_path: Path) -> None:
    env, inner = _wrapper(tmp_path)
    env.reset()
    inner.set_ram({"room": "0x00", "stage": 1})
    _, r1, *_ = env.step(0)
    inner.set_ram({"room": "0x00", "stage": 3})
    _, r2, *_ = env.step(0)
    assert r1 == 100.0
    assert r2 == 100.0
    assert env.episode_reward == 200.0
