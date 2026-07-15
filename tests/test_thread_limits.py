"""Unit tests for train thread limits (FAIL_REPORT R3.1)."""
from __future__ import annotations

import os
from unittest.mock import MagicMock

from train.thread_limits import MAX_THREADS_HIGH_ENV, configure_train_threads


def test_configure_train_threads_caps_at_6_envs(monkeypatch) -> None:
    monkeypatch.setattr("train.thread_limits.torch.set_num_threads", MagicMock())
    result = configure_train_threads(n_envs=6, threads=4)
    assert result["torch_threads"] == MAX_THREADS_HIGH_ENV
    assert os.environ["OPENBLAS_NUM_THREADS"] == str(MAX_THREADS_HIGH_ENV)


def test_configure_train_threads_caps_at_8_envs(monkeypatch) -> None:
    monkeypatch.setattr("train.thread_limits.torch.set_num_threads", MagicMock())
    result = configure_train_threads(n_envs=8, threads=4)
    assert result["torch_threads"] == MAX_THREADS_HIGH_ENV
    assert os.environ["OPENBLAS_NUM_THREADS"] == str(MAX_THREADS_HIGH_ENV)
    assert os.environ["OMP_NUM_THREADS"] == str(MAX_THREADS_HIGH_ENV)


def test_configure_train_threads_allows_higher_below_cap(monkeypatch) -> None:
    monkeypatch.setattr("train.thread_limits.torch.set_num_threads", MagicMock())
    result = configure_train_threads(n_envs=4, threads=4)
    assert result["torch_threads"] == 4
    assert os.environ["OPENBLAS_NUM_THREADS"] == "4"
