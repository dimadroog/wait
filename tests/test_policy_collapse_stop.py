"""Unit: PolicyCollapseStopCallback (автостоп по entropy + approx_kl)."""
from __future__ import annotations

from unittest.mock import MagicMock

from train.policy_collapse_stop import (
    PolicyCollapseStopCallback,
    is_policy_collapse_metrics,
)


def test_is_policy_collapse_metrics_thresholds() -> None:
    assert is_policy_collapse_metrics(-0.0004, 0.0) is True
    assert is_policy_collapse_metrics(-0.4, 0.0) is False
    assert is_policy_collapse_metrics(-0.0004, 0.001) is False
    assert is_policy_collapse_metrics(None, 0.0) is False
    assert is_policy_collapse_metrics(-0.0004, None) is False


def _cb_with_logger(
    entropy: float | None, kl: float | None, *, streak: int = 3
) -> PolicyCollapseStopCallback:
    cb = PolicyCollapseStopCallback(streak=streak, verbose=0)
    values: dict[str, float] = {}
    if entropy is not None:
        values["train/entropy_loss"] = entropy
    if kl is not None:
        values["train/approx_kl"] = kl
    logger = MagicMock()
    logger.name_to_value = values
    cb.model = MagicMock()
    cb.model.logger = logger
    return cb


def test_skips_until_train_metrics_appear() -> None:
    cb = _cb_with_logger(None, None, streak=2)
    cb._on_rollout_end()
    assert cb._dead_streak == 0
    assert cb.stopped is False
    assert cb._on_step() is True


def test_stops_after_dead_streak() -> None:
    cb = _cb_with_logger(-0.0005, 0.0, streak=3)
    cb._on_rollout_end()
    assert cb.stopped is False
    cb._on_rollout_end()
    assert cb.stopped is False
    cb._on_rollout_end()
    assert cb.stopped is True
    assert cb._dead_streak == 3
    assert cb._on_step() is False


def test_alive_metrics_reset_streak() -> None:
    cb = _cb_with_logger(-0.0005, 0.0, streak=3)
    cb._on_rollout_end()
    cb._on_rollout_end()
    cb.model.logger.name_to_value = {
        "train/entropy_loss": -0.4,
        "train/approx_kl": 0.001,
    }
    cb._on_rollout_end()
    assert cb._dead_streak == 0
    assert cb.stopped is False
    assert cb._on_step() is True
