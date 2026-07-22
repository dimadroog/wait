"""Сводка inference_inputs: noop_frac и гистограмма action."""
from __future__ import annotations

import json
from pathlib import Path

from inference_action_stats import (
    is_noop_action,
    resolve_inputs_path,
    summarize_inference_actions,
    summarize_path,
)


def test_is_noop_action() -> None:
    assert is_noop_action("")
    assert is_noop_action("  ")
    assert is_noop_action(None)
    assert not is_noop_action("right")
    assert not is_noop_action("A")


def test_summarize_noop_frac_and_hist() -> None:
    rows = [
        {"episode": 1, "step": 0, "action": ""},
        {"episode": 1, "step": 1, "action": "right"},
        {"episode": 1, "step": 2, "action": ""},
        {"episode": 2, "step": 0, "action": "A"},
        {"episode": 2, "step": 1, "action": "right"},
    ]
    summary = summarize_inference_actions(rows)
    assert summary["n_steps"] == 5
    assert summary["noop"] == 2
    assert summary["noop_frac"] == 0.4
    assert summary["action_hist"][""] == 2
    assert summary["action_hist"]["right"] == 2
    assert summary["action_hist"]["A"] == 1
    assert summary["n_episodes"] == 2
    assert summary["episodes"][0]["noop_frac"] == 0.6667
    assert summary["episodes"][1]["noop_frac"] == 0.0


def test_summarize_with_attempts_max_checkpoint() -> None:
    inputs = [
        {"episode": 1, "step": 0, "action": ""},
        {"episode": 1, "step": 1, "action": "right"},
        {"episode": 2, "step": 0, "action": ""},
    ]
    attempts = [
        {"episode": 1, "max_checkpoint": 2},
        {"episode": 2, "max_checkpoint": 4},
    ]
    summary = summarize_inference_actions(inputs, attempt_rows=attempts)
    assert summary["episodes"][0]["max_checkpoint"] == 2
    assert summary["episodes"][1]["max_checkpoint"] == 4
    assert summary["max_checkpoint_mean"] == 3.0
    assert summary["max_checkpoint_max"] == 4
    assert summary["max_checkpoint_min"] == 2


def test_summarize_path_day_dir(tmp_path: Path) -> None:
    day = tmp_path / "20260722"
    day.mkdir()
    inputs = day / "inference_inputs.jsonl"
    attempts = day / "attempts.jsonl"
    inputs.write_text(
        "\n".join(
            [
                json.dumps({"episode": 1, "step": 0, "action": ""}),
                json.dumps({"episode": 1, "step": 1, "action": "B"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    attempts.write_text(
        json.dumps({"episode": 1, "max_checkpoint": 3}) + "\n",
        encoding="utf-8",
    )
    assert resolve_inputs_path(day) == inputs
    summary = summarize_path(day)
    assert summary["noop_frac"] == 0.5
    assert summary["max_checkpoint_max"] == 3
    assert Path(summary["attempts_path"]) == attempts
