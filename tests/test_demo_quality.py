"""Тесты demo_quality."""
from __future__ import annotations

import json

import numpy as np
import pytest

from demo_quality import (
    compute_metrics,
    is_black_frame,
    is_gameplay_like_frame,
    validate_demo_npz,
)
from obs_contract import OBS_SHAPE, obs_frame_shape


def test_black_frame_detection() -> None:
    h, w = obs_frame_shape()
    black = np.zeros((h, w), dtype=np.float32)
    gameplay = np.full((h, w), 0.5, dtype=np.float32)
    gameplay[40:50, 20:60] = 0.9
    assert is_black_frame(black)
    assert not is_black_frame(gameplay)
    assert is_gameplay_like_frame(gameplay)
    assert not is_gameplay_like_frame(black)


def test_compute_metrics_mixed() -> None:
    obs = np.zeros((10, *OBS_SHAPE), dtype=np.float32)
    obs[0, -1] = 0.6
    m = compute_metrics(obs)
    assert m.n_steps == 10
    assert m.black_fraction == 0.9
    assert not m.passed


def test_validate_demo_npz_gameplay_segment(tmp_path: Path) -> None:
    obs = np.zeros((5, *OBS_SHAPE), dtype=np.float32)
    for i in range(5):
        obs[i, -1, :, :] = 0.3 + 0.1 * i
        obs[i, -1, 40:50, 20:60] = 0.9
    meta = json.dumps(
        {
            "segment_id": "seg_002",
            "frame_start": 1034,
            "frame_end": 2000,
            "frame_skip": 4,
            "record_mode": "fm2_playmovie",
        }
    )
    path = tmp_path / "seg_002.npz"
    np.savez_compressed(path, obs=obs, actions=np.zeros(5, dtype=np.int64), meta=np.array(meta))
    result = validate_demo_npz(path, gameplay_start_frame=1034)
    assert result.require_gameplay
    assert result.passed


def test_validate_demo_npz_fails_on_black(tmp_path: Path) -> None:
    obs = np.zeros((20, *OBS_SHAPE), dtype=np.float32)
    meta = json.dumps({"segment_id": "seg_002", "frame_start": 1034})
    path = tmp_path / "seg_002.npz"
    np.savez_compressed(path, obs=obs, actions=np.zeros(20, dtype=np.int64), meta=np.array(meta))
    result = validate_demo_npz(path, gameplay_start_frame=1034)
    assert not result.passed
    assert result.failure_reasons()


def test_validate_demo_npz_rejects_wrong_shape(tmp_path: Path) -> None:
    obs = np.zeros((2, 4, 64, 64), dtype=np.float32)
    meta = json.dumps({"segment_id": "seg_bad", "frame_start": 0})
    path = tmp_path / "seg_bad.npz"
    np.savez_compressed(path, obs=obs, actions=np.zeros(2, dtype=np.int64), meta=np.array(meta))
    with pytest.raises(ValueError, match="expected obs shape"):
        validate_demo_npz(path)
