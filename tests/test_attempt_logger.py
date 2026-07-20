"""Unit tests for AttemptLogger end-of-episode fields."""
from __future__ import annotations

import json
from pathlib import Path

from attempt_logger import AttemptLogger


def test_log_episode_writes_terminate_reason_and_death_count(tmp_path: Path) -> None:
    logger = AttemptLogger(tmp_path)
    record = logger.log_episode(
        mission="1",
        episode=3,
        info={
            "died": True,
            "death_count": 2,
            "terminate_reason": "death",
            "episode_frames": 100,
            "episode_reward": 12.5,
            "max_checkpoint": 4,
            "ram": {"x": 129, "y": 131, "room": "0x0F", "lives": 5, "hp": 7},
        },
        model_version="gen0",
    )
    assert record["terminate_reason"] == "death"
    assert record["death_count"] == 2
    assert record["death_lives"] == 5
    assert record["death_room"] == "0x0F"

    lines = logger.log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    loaded = json.loads(lines[0])
    assert loaded["terminate_reason"] == "death"
    assert loaded["death_count"] == 2
    assert loaded["death_lives"] == 5


def test_log_episode_end_lives_without_died(tmp_path: Path) -> None:
    logger = AttemptLogger(tmp_path)
    record = logger.log_episode(
        mission="1",
        episode=1,
        info={
            "died": False,
            "death_count": 0,
            "terminate_reason": "title_screen",
            "episode_frames": 50,
            "episode_reward": 1.0,
            "ram": {"x": 129, "y": 0, "room": "0x00", "lives": 0},
        },
    )
    assert record["died"] is False
    assert record["terminate_reason"] == "title_screen"
    assert record["death_count"] == 0
    assert record["death_lives"] == 0
    assert record["death_hp"] is None
