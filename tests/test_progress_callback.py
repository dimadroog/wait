from unittest.mock import MagicMock

from train.progress_callback import TrainProgressPctCallback


def test_progress_callback_records_time_section() -> None:
    cb = TrainProgressPctCallback(500_000)
    model = MagicMock()
    model.num_timesteps = 1280
    model.logger = MagicMock()
    cb.model = model

    cb._on_rollout_end()

    model.logger.record.assert_any_call("time/progress_pct", 0.3, exclude="tensorboard")
    model.logger.record.assert_any_call("time/target_timesteps", 500_000, exclude="tensorboard")


def test_progress_callback_caps_at_100() -> None:
    cb = TrainProgressPctCallback(1000)
    model = MagicMock()
    model.num_timesteps = 1500
    model.logger = MagicMock()
    cb.model = model

    cb._on_rollout_end()

    model.logger.record.assert_any_call("time/progress_pct", 100.0, exclude="tensorboard")


def test_progress_callback_session_window_after_reset() -> None:
    """model-in + reset: бюджет remaining=30k → 15k шагов = 50%."""
    cb = TrainProgressPctCallback(30_000, start_timesteps=0)
    model = MagicMock()
    model.num_timesteps = 15_000
    model.logger = MagicMock()
    cb.model = model

    cb._on_rollout_end()

    model.logger.record.assert_any_call("time/progress_pct", 50.0, exclude="tensorboard")
    model.logger.record.assert_any_call("time/target_timesteps", 30_000, exclude="tensorboard")


def test_progress_callback_resume_window() -> None:
    """resume: от 715284 к 745284 → +15k из +30k ≈ 50%."""
    cb = TrainProgressPctCallback(745_284, start_timesteps=715_284)
    model = MagicMock()
    model.num_timesteps = 715_284 + 15_000
    model.logger = MagicMock()
    cb.model = model

    cb._on_rollout_end()

    model.logger.record.assert_any_call("time/progress_pct", 50.0, exclude="tensorboard")
