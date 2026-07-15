"""Прогресс train в таблице SB3 (секция time/)."""
from __future__ import annotations

from stable_baselines3.common.callbacks import BaseCallback


class TrainProgressPctCallback(BaseCallback):
    """Пишет `time/progress_pct` и `time/target_timesteps` перед dump_logs SB3."""

    def __init__(self, target_timesteps: int):
        super().__init__(verbose=0)
        self.target_timesteps = max(int(target_timesteps), 1)

    def _record_progress(self) -> None:
        done = int(self.model.num_timesteps)
        pct = min(100.0, 100.0 * done / self.target_timesteps)
        self.logger.record("time/progress_pct", round(pct, 1), exclude="tensorboard")
        self.logger.record("time/target_timesteps", self.target_timesteps, exclude="tensorboard")

    def _on_step(self) -> bool:
        return True

    def _on_rollout_end(self) -> bool:
        self._record_progress()
        return True
