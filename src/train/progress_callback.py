"""Консольный прогресс train в % (BACKLOG 1.4)."""
from __future__ import annotations

import sys
import time

from stable_baselines3.common.callbacks import BaseCallback


class TrainProgressPctCallback(BaseCallback):
    """Печать `train: 42.3% (211500/500000 steps)` с throttling (не чаще min_interval_sec)."""

    def __init__(
        self,
        target_timesteps: int,
        *,
        min_interval_sec: float = 5.0,
        file=None,
    ):
        super().__init__(verbose=0)
        self.target_timesteps = max(int(target_timesteps), 1)
        self.min_interval_sec = min_interval_sec
        self.file = file or sys.stderr
        self._last_print = 0.0

    def _format_line(self) -> str:
        done = int(self.model.num_timesteps)
        target = self.target_timesteps
        pct = min(100.0, 100.0 * done / target)
        return f"train: {pct:.1f}% ({done}/{target} steps)"

    def _emit(self, *, newline: bool = False) -> None:
        end = "\n" if newline else "\r"
        print(self._format_line(), end=end, flush=True, file=self.file)

    def _on_step(self) -> bool:
        return True

    def _on_training_start(self) -> None:
        self._last_print = 0.0
        self._emit(newline=True)

    def _on_rollout_end(self) -> bool:
        now = time.monotonic()
        if now - self._last_print < self.min_interval_sec:
            return True
        self._last_print = now
        self._emit(newline=False)
        return True

    def _on_training_end(self) -> None:
        self._emit(newline=True)
