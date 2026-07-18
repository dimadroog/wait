"""Unit tests for H4 learn chunking."""
from __future__ import annotations

from train.recycle import iter_learn_chunks


def test_no_recycle_single_chunk() -> None:
    assert iter_learn_chunks(10_000, 0) == [10_000]
    assert iter_learn_chunks(10_000, -1) == [10_000]


def test_recycle_splits_evenly() -> None:
    assert iter_learn_chunks(10_000, 4_000) == [4_000, 4_000, 2_000]


def test_empty_remaining() -> None:
    assert iter_learn_chunks(0, 1000) == []
