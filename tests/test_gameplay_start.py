"""Unit tests for etalon build config and gameplay start (Strategy in plugin YAML)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from etalon_build_config import (  # noqa: E402
    GameplayStartRule,
    load_etalon_build_config,
    rewards_default_from_etalon_build,
)
from playthrough_build import (  # noqa: E402
    gameplay_start_frame_from_head_saves,
    head_save_state_plan,
    load_head_save_states,
    load_human_playthrough_rows,
    plan_segments,
    save_state_plan,
)


def test_rushn_attack_has_no_etalon_build() -> None:
    """RnA: канон якорей — head_save_states; etalon_build.yaml не шумит."""
    assert load_etalon_build_config("rushn_attack") is None


def test_rewards_default_without_etalon_yaml() -> None:
    rewards = rewards_default_from_etalon_build({})
    assert rewards["death_penalty"] == 40


def test_gameplay_start_frame_m1_from_head_saves() -> None:
    """Старт геймплея m1 — ручной якорь cp_gameplay0 (не эвристика etalon_build)."""
    mission = Path(__file__).resolve().parents[1] / "games" / "rushn_attack" / "missions" / "m1"
    heads = load_head_save_states(mission)
    frame = gameplay_start_frame_from_head_saves(heads)
    assert frame == 1243
    rows = load_human_playthrough_rows(mission / "reference" / "human_playthrough.jsonl")
    start = rows[frame - 1]
    assert 1 <= int(start["lives"]) <= 9
    assert str(start["room"]).upper() == "0X00"


def test_m1_head_save_states_manual_anchors() -> None:
    mission = Path(__file__).resolve().parents[1] / "games" / "rushn_attack" / "missions" / "m1"
    heads = load_head_save_states(mission)
    assert heads is not None
    assert gameplay_start_frame_from_head_saves(heads) == 1243
    plan = head_save_state_plan(heads)
    by_file = {e["file"]: e for e in plan}
    assert by_file["cp_title0.fc0"]["frame"] == 20
    assert by_file["cp_intro0.fc0"]["frame"] == 358
    assert by_file["cp_gameplay0.fc0"]["frame"] == 1243
    assert by_file["cp_gameplay1.fc0"]["frame"] == 1506
    assert by_file["cp_bossfight0.fc0"]["frame"] == 4330
    assert by_file["cp_intro1.fc0"]["frame"] == 5492
    assert [e["frame"] for e in plan] == sorted(e["frame"] for e in plan)
    assert "etalon_start.fc0" not in by_file
    assert "inference_cp0.fc0" not in by_file
    assert "cp0.fc0" not in by_file


def test_gameplay_start_rule_rejects_unknown_input_kind() -> None:
    with pytest.raises(ValueError, match="require_input"):
        GameplayStartRule(require_input="teleport")


def test_plan_segments_title_then_gameplay_axis() -> None:
    segs = plan_segments(1000, 5, gameplay_start_frame=200)
    assert len(segs) == 5
    assert segs[0]["frame_start"] == 1 and segs[0]["frame_end"] == 199
    assert segs[1]["frame_start"] == 200
    for seg in segs[1:]:
        assert seg["frame_start"] >= 200
    assert segs[-1]["frame_end"] == 1000


def test_save_state_plan_requires_head_saves() -> None:
    segs = plan_segments(500, 3, gameplay_start_frame=100)
    with pytest.raises(ValueError, match="head_save_states required"):
        save_state_plan(segs, gameplay_start_frame=100, head_save_states=None)


def test_save_state_plan_from_head_saves() -> None:
    heads = {
        "title": [{"id": "cp_title0", "frame": 20}],
        "gameplay": [{"id": "cp_gameplay0", "frame": 100}],
    }
    plan = save_state_plan([], head_save_states=heads)
    assert [e["file"] for e in plan] == ["cp_title0.fc0", "cp_gameplay0.fc0"]
