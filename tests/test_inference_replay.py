"""Unit tests for inference jsonl replay (BACKLOG 3.4)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from inference_replay import episode_action_digest, episode_step_actions, replay_frame_count  # noqa: E402


def test_episode_step_actions_expands_frame_skip(tmp_path: Path) -> None:
    p = tmp_path / "inputs.jsonl"
    p.write_text(
        "\n".join(
            [
                json.dumps({"episode": 1, "action": "right"}),
                json.dumps({"episode": 1, "action": "left"}),
                json.dumps({"episode": 2, "action": "up"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    steps = episode_step_actions(p, 1, frame_skip=4)
    assert steps == ["right"] * 4 + ["left"] * 4
    assert replay_frame_count(p, 1, frame_skip=4) == 8
    assert episode_action_digest(p, 1) != episode_action_digest(p, 2)
