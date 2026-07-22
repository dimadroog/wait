"""Прогресс train в таблице SB3 (секция time/)."""
from __future__ import annotations

from stable_baselines3.common.callbacks import BaseCallback


class TrainProgressPctCallback(BaseCallback):
    """Пишет `time/progress_pct` и `time/target_timesteps` перед dump_logs SB3.

    ``progress_pct = 100 * (num_timesteps - start) / (target - start)``.

    При ``reset_num_timesteps`` (новый PPO или ``--model-in``) передавайте
    ``start_timesteps=0`` и ``target_timesteps=remaining``, чтобы шкала была
    0→100% по бюджету текущего прогона, а не по абсолютной цели CLI.
    При ``--resume`` — ``start`` = текущий счётчик, ``target`` = абсолютная цель.
    """

    def __init__(self, target_timesteps: int, *, start_timesteps: int = 0):
        super().__init__(verbose=0)
        self.target_timesteps = max(int(target_timesteps), 1)
        self.start_timesteps = max(int(start_timesteps), 0)

    def _record_progress(self) -> None:
        done = int(self.model.num_timesteps)
        span = max(self.target_timesteps - self.start_timesteps, 1)
        pct = min(100.0, 100.0 * max(done - self.start_timesteps, 0) / span)
        self.logger.record("time/progress_pct", round(pct, 1), exclude="tensorboard")
        self.logger.record("time/target_timesteps", self.target_timesteps, exclude="tensorboard")

    def _on_step(self) -> bool:
        return True

    def _on_rollout_end(self) -> bool:
        self._record_progress()
        return True
