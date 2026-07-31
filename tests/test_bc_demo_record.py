"""Тесты bc_demo_record (без FCEUX)."""
from __future__ import annotations

import json
from collections import deque
from pathlib import Path

import numpy as np

from bc_demo_record import (
    SampleRow,
    _obs_stack_from_deque,
    _partition_samples,
    load_sample_rows,
)
from obs_contract import OBS_RAW_BYTES, OBS_SHAPE, obs_frame_shape


def test_obs_stack_pads_short_deque() -> None:
    h, w = obs_frame_shape()
    gray = np.full((h, w), 128, dtype=np.uint8)
    d: deque[np.ndarray] = deque([gray], maxlen=4)
    stack = _obs_stack_from_deque(d)
    assert stack.shape == OBS_SHAPE
    assert stack.max() > 0.4


def test_partition_samples_assigns_segments(tmp_path: Path) -> None:
    obs_a = tmp_path / "a.raw"
    obs_b = tmp_path / "b.raw"
    obs_a.write_bytes(np.full(OBS_RAW_BYTES, 200, dtype=np.uint8).tobytes())
    obs_b.write_bytes(np.full(OBS_RAW_BYTES, 100, dtype=np.uint8).tobytes())

    rows = [
        SampleRow(frame=10, obs_path=obs_a),
        SampleRow(frame=14, obs_path=obs_b),
    ]
    segments = [
        {"id": "seg_001", "frame_start": 10, "frame_end": 20},
        {"id": "seg_002", "frame_start": 30, "frame_end": 40},
    ]
    human = {10: "left", 14: "right"}
    partitioned = _partition_samples(
        rows,
        segments=segments,
        human_by_frame=human,
        action_strings=["", "left", "right"],
        frame_skip=4,
    )
    obs, actions = partitioned["seg_001"]
    assert obs.shape[0] == 2
    assert actions.shape[0] == 2
    assert partitioned["seg_002"][0].shape[0] == 0


def test_load_sample_rows(tmp_path: Path) -> None:
    path = tmp_path / "samples.jsonl"
    path.write_text(
        '{"frame": 4, "obs": "C:/tmp/obs_000004.raw"}\n'
        '{"frame": 8, "obs": "C:/tmp/obs_000008.raw"}\n',
        encoding="utf-8",
    )
    rows = load_sample_rows(path)
    assert [r.frame for r in rows] == [4, 8]
