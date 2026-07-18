"""Смягчение RAM pressure при длинном train (ISSUE_TRAIN_FPS_DEGRADATION H2, ISSUE_FALL R3.3)."""
from __future__ import annotations

import gc

from stable_baselines3.common.callbacks import BaseCallback

# Эталонная среда: i7-3770, 16 GB. Gate/benchmark — n_envs=8; длинный train — 6.
DEFAULT_N_ENVS_16GB = 6
REFERENCE_RAM_GB = 16


def warn_if_n_envs_high_for_ram(
    n_envs: int,
    *,
    recommended: int = DEFAULT_N_ENVS_16GB,
    ram_gb: int = REFERENCE_RAM_GB,
) -> None:
    if n_envs > recommended:
        print(
            f"WARNING [H2]: n_envs={n_envs} на ~{ram_gb} GB RAM — "
            f"для длинного train рекомендуется --n-envs {recommended} "
            "(docs/tasks/archive/TASK_TRAIN_FPS_DEGRADATION.md)"
        )


class RolloutGcCallback(BaseCallback):
    """on_rollout_end → gc.collect() для снижения фрагментации RAM между rollout'ами."""

    def __init__(self, verbose: int = 0):
        super().__init__(verbose)

    def _on_step(self) -> bool:
        return True

    def _on_rollout_end(self) -> bool:
        gc.collect()
        return True
