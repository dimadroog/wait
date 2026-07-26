"""Unit tests for etalon build config and gameplay start (Strategy in plugin YAML)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from etalon_build_config import (  # noqa: E402
    GameplayStartRule,
    gameplay_start_rule_from_etalon_build,
    load_etalon_build_config,
    rewards_default_from_etalon_build,
    transition_rooms_from_etalon_build,
)
from playthrough_build import (  # noqa: E402
    gameplay_start_frame_from_head_saves,
    gameplay_start_frame_from_rows,
    head_save_state_plan,
    load_head_save_states,
    load_human_playthrough_rows,
    plan_segments,
    save_state_plan,
)


def test_etalon_build_config_rushn_attack() -> None:
    etalon_build = load_etalon_build_config("rushn_attack")
    rooms = transition_rooms_from_etalon_build(etalon_build)
    assert 0xFF in rooms
    assert 0x00 not in rooms
    assert etalon_build.get("segment_count") == 5
    assert len(etalon_build.get("checkpoint_heuristics", [])) >= 1
    rule = gameplay_start_rule_from_etalon_build(etalon_build)
    assert rule.lives_min == 1 and rule.lives_max == 9
    assert rule.require_input == "move_or_attack"
    rewards = rewards_default_from_etalon_build(etalon_build)
    assert rewards["death_penalty"] == 40


def test_gameplay_start_frame_m1_heuristic() -> None:
    """Авто-эвристика etalon_build (может отличаться от ручного якоря 1243)."""
    mission = Path(__file__).resolve().parents[1] / "games" / "rushn_attack" / "missions" / "m1"
    etalon_build = load_etalon_build_config("rushn_attack")
    rows = load_human_playthrough_rows(mission / "reference" / "human_playthrough.jsonl")
    rule = gameplay_start_rule_from_etalon_build(etalon_build)
    frame = gameplay_start_frame_from_rows(
        rows,
        transition_rooms=transition_rooms_from_etalon_build(etalon_build),
        rule=rule,
    )
    assert frame == 1250
    start = rows[frame - 1]
    assert 1 <= int(start["lives"]) <= 9
    assert "right" in str(start.get("action", "")).lower()
    assert int(str(start["room"]), 16) not in transition_rooms_from_etalon_build(
        etalon_build
    )


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
