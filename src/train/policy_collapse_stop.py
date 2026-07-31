"""Автостоп PPO при схлопе политики (entropy + approx_kl)."""
from __future__ import annotations

from typing import Any

from stable_baselines3.common.callbacks import BaseCallback

# Пороги — docs/TRAIN_ANALYSIS.md § практическое правило остановки.
DEFAULT_ENTROPY_ABS_MAX = 0.01
DEFAULT_APPROX_KL_MAX = 1e-8
DEFAULT_COLLAPSE_STREAK = 10


def is_policy_collapse_metrics(
    entropy_loss: float | None,
    approx_kl: float | None,
    *,
    entropy_abs_max: float = DEFAULT_ENTROPY_ABS_MAX,
    approx_kl_max: float = DEFAULT_APPROX_KL_MAX,
) -> bool:
    """True если оба сигнала схлопа на месте (метрики уже есть)."""
    if entropy_loss is None or approx_kl is None:
        return False
    return abs(float(entropy_loss)) < float(entropy_abs_max) and float(approx_kl) < float(
        approx_kl_max
    )


class PolicyCollapseStopCallback(BaseCallback):
    """После rollout читает train/entropy_loss и train/approx_kl (с прошлого update).

    При N «мёртвых» подряд выставляет ``stopped``; следующий ``_on_step`` возвращает
    False и останавливает collect/learn (в SB3 return из ``_on_rollout_end`` не стопает).
    Включено по умолчанию в train_ppo без CLI.
    """

    def __init__(
        self,
        *,
        streak: int = DEFAULT_COLLAPSE_STREAK,
        entropy_abs_max: float = DEFAULT_ENTROPY_ABS_MAX,
        approx_kl_max: float = DEFAULT_APPROX_KL_MAX,
        verbose: int = 1,
    ) -> None:
        super().__init__(verbose=verbose)
        self._streak_needed = max(int(streak), 1)
        self._entropy_abs_max = float(entropy_abs_max)
        self._approx_kl_max = float(approx_kl_max)
        self._dead_streak = 0
        self.stopped = False
        self.last_entropy: float | None = None
        self.last_approx_kl: float | None = None
        self._stop_announced = False

    def _read_train_metrics(self) -> tuple[float | None, float | None]:
        values: dict[str, Any] = {}
        logger = getattr(self.model, "logger", None)
        if logger is not None:
            values = getattr(logger, "name_to_value", None) or {}
        try:
            ent = values.get("train/entropy_loss")
            kl = values.get("train/approx_kl")
            ent_f = float(ent) if ent is not None else None
            kl_f = float(kl) if kl is not None else None
        except (TypeError, ValueError):
            return None, None
        return ent_f, kl_f

    def _on_step(self) -> bool:
        return not self.stopped

    def _on_rollout_end(self) -> None:
        if self.stopped:
            return
        entropy_loss, approx_kl = self._read_train_metrics()
        self.last_entropy = entropy_loss
        self.last_approx_kl = approx_kl
        if entropy_loss is None or approx_kl is None:
            return
        if is_policy_collapse_metrics(
            entropy_loss,
            approx_kl,
            entropy_abs_max=self._entropy_abs_max,
            approx_kl_max=self._approx_kl_max,
        ):
            self._dead_streak += 1
        else:
            self._dead_streak = 0
        if self._dead_streak < self._streak_needed:
            return
        self.stopped = True
        if not self._stop_announced:
            self._stop_announced = True
            print(
                "policy collapse stop: "
                f"|entropy_loss|={abs(entropy_loss):.6g} < {self._entropy_abs_max}, "
                f"approx_kl={approx_kl:.6g} < {self._approx_kl_max}, "
                f"streak={self._dead_streak}/{self._streak_needed}"
            )
