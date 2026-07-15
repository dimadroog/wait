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
