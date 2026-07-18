"""Unit tests for LatestCheckpointCallback throttling (H5)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from train.checkpointing import LatestCheckpointCallback


def test_saves_every_rollout_when_every_is_1(tmp_path: Path) -> None:
    path = tmp_path / "latest.zip"
    cb = LatestCheckpointCallback(path, every_rollouts=1)
    cb.model = MagicMock()
    with patch("train.checkpointing.atomic_save_model") as save:
        for _ in range(3):
            assert cb._on_rollout_end() is True
        assert save.call_count == 3


def test_throttles_to_every_n_rollouts(tmp_path: Path) -> None:
    path = tmp_path / "latest.zip"
    cb = LatestCheckpointCallback(path, every_rollouts=5)
    cb.model = MagicMock()
    with patch("train.checkpointing.atomic_save_model") as save:
        for _ in range(12):
            cb._on_rollout_end()
        assert save.call_count == 2  # rollouts 5 and 10
        assert cb._rollout_idx == 12


def test_every_rollouts_clamped_to_at_least_one(tmp_path: Path) -> None:
    cb = LatestCheckpointCallback(tmp_path / "latest.zip", every_rollouts=0)
    assert cb._every == 1
