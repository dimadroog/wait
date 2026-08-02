"""Unit-тесты bc_open_loop_eval (без FCEUX)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from bc_open_loop_eval import (
    AttackWindowRow,
    ClosedLoopReport,
    FrameAction,
    MatchStats,
    OpenLoopReport,
    build_transfer_verdict,
    evaluate_closed_loop_from_logs,
    evaluate_open_loop,
    load_human_playthrough,
    parse_attack_window,
    update_match_stats,
)
from train.action_map import action_string_to_index


_ACTIONS = ["", "right", "left", "up", "down", "B", "A", "right+up"]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n",
        encoding="utf-8",
    )


def test_load_human_playthrough_frame_skip(tmp_path: Path) -> None:
    human = tmp_path / "human_playthrough.jsonl"
    rows = [
        {"frame": 1034, "action": ""},
        {"frame": 1035, "action": "right"},
        {"frame": 1038, "action": "left"},
        {"frame": 1042, "action": "B"},
        {"frame": 1100, "action": "A"},
    ]
    _write_jsonl(human, rows)

    loaded = load_human_playthrough(
        tmp_path,
        frame_start=1034,
        frame_end=1100,
        frame_skip=4,
        action_strings=_ACTIONS,
        human_path=human,
    )
    assert [fa.frame for fa in loaded] == [1034, 1038, 1042]
    assert loaded[2].action == "B"
    assert loaded[2].action_index == action_string_to_index("B", _ACTIONS)


def test_closed_loop_align_by_frame(tmp_path: Path) -> None:
    human = tmp_path / "human.jsonl"
    inference = tmp_path / "inference_inputs.jsonl"
    _write_jsonl(
        human,
        [
            {"frame": 1100, "action": "right"},
            {"frame": 1104, "action": "B"},
        ],
    )
    _write_jsonl(
        inference,
        [
            {"episode": 1, "step": 99, "frame": 1100, "action": "right"},
            {"episode": 1, "step": 5, "frame": 1104, "action": "left"},
            {"episode": 2, "step": 1, "frame": 1100, "action": "A"},
        ],
    )

    report = evaluate_closed_loop_from_logs(
        inference,
        human,
        _ACTIONS,
        frame_start=1100,
        frame_end=1104,
        frame_skip=4,
        attack_window=(1100, 1104),
        episode=1,
    )
    assert report.stats.total == 2
    assert report.stats.correct == 1
    assert report.stats.b_total == 1
    assert report.stats.b_correct == 0


def test_attack_window_stats() -> None:
    stats = MatchStats(0, 0, 0, 0, 0, 0)
    stats = update_match_stats(
        stats,
        pred_index=5,
        human_index=5,
        human_action="B",
        action_strings=_ACTIONS,
        noop_action_index=0,
        frame=1200,
        attack_window=(1195, 1210),
    )
    assert stats.b_correct == 1
    assert stats.b_total == 1
    assert stats.attack_window_correct == 1
    assert stats.attack_window_b_correct == 1

    stats = update_match_stats(
        stats,
        pred_index=1,
        human_index=5,
        human_action="B",
        action_strings=_ACTIONS,
        noop_action_index=0,
        frame=1300,
        attack_window=(1195, 1210),
    )
    assert stats.b_correct == 1
    assert stats.b_total == 2
    assert stats.attack_window_total == 1


@pytest.mark.parametrize(
    ("open_b", "closed_b", "open_total", "closed_total", "intro_phase", "expected"),
    [
        (85.0, 10.0, 95.0, 20.0, False, "TRAJECTORY_DRIFT"),
        (30.0, 80.0, 95.0, 20.0, False, "BC_OBS_HEAD"),
        (70.0, 70.0, 95.0, 20.0, False, "DISTRIBUTION_SHIFT"),
        (70.0, 70.0, 60.0, 40.0, True, "PHASE_BUG"),
    ],
)
def test_build_transfer_verdict_rules(
    open_b: float,
    closed_b: float,
    open_total: float,
    closed_total: float,
    intro_phase: bool,
    expected: str,
) -> None:
    open_stats = MatchStats(
        correct=int(open_total),
        total=100,
        noop_correct=0,
        noop_total=0,
        move_correct=int(open_total),
        move_total=100,
        b_correct=int(open_b),
        b_total=100,
    )
    closed_stats = MatchStats(
        correct=int(closed_total),
        total=100,
        noop_correct=0,
        noop_total=0,
        move_correct=int(closed_total),
        move_total=100,
        attack_window_b_correct=int(closed_b),
        attack_window_b_total=100,
    )
    phase_id = "intro" if intro_phase else "gameplay"
    open_report = OpenLoopReport(
        stats=open_stats,
        attack_rows=(
            AttackWindowRow(
                frame=1200,
                human_action="B",
                open_loop_pred="B",
                phase_id=phase_id,
                head_id="gameplay",
            ),
        ),
        frame_start=1034,
        frame_end=1300,
        attack_window=(1195, 1210),
    )
    closed_report = ClosedLoopReport(
        stats=closed_stats,
        attack_rows=(),
        episode=1,
        frame_start=1034,
        frame_end=1300,
        attack_window=(1195, 1210),
    )
    verdict = build_transfer_verdict(open_report, closed_report)
    assert verdict.label == expected


def test_build_transfer_verdict_obs_pipeline_mismatch() -> None:
    from bc_open_loop_eval import MatchStats, NpzOfflineReport, OpenLoopReport

    npz = NpzOfflineReport(
        segment_id="seg_002",
        stats=MatchStats(430, 466, 200, 210, 230, 256, 40, 42),
    )
    open_rep = OpenLoopReport(
        stats=MatchStats(34, 67, 34, 35, 0, 32),
        attack_rows=(),
        frame_start=1034,
        frame_end=1300,
        attack_window=(1195, 1210),
    )
    verdict = build_transfer_verdict(open_rep, None, npz_offline=npz)
    assert verdict.label == "OBS_PIPELINE_MISMATCH"
    assert "obs_pipeline_mismatch" in verdict.rules_triggered


def test_evaluate_open_loop_mock_predict() -> None:
    human_frames = [
        FrameAction(frame=1034, action="", action_index=0),
        FrameAction(frame=1038, action="right", action_index=1),
    ]
    env = MagicMock()
    env.reset.return_value = (
        np.zeros((4, 84, 84), dtype=np.float32),
        {"ram": {"frame": 1034}, "phase_id": "gameplay"},
    )
    env.step.side_effect = [
        (np.zeros((4, 84, 84), dtype=np.float32), 0.0, False, False, {"ram": {"frame": 1038}, "phase_id": "gameplay"}),
        (np.zeros((4, 84, 84), dtype=np.float32), 0.0, False, False, {"ram": {"frame": 1042}, "phase_id": "gameplay"}),
    ]

    model = MagicMock()
    model.predict.side_effect = [(np.array([0]), None), (np.array([1]), None)]

    def fake_predict(model, obs, phase_id, heads_spec, deterministic=True):
        action, state = model.predict(obs, deterministic=deterministic)
        return action, state, "gameplay"

    import bc_open_loop_eval as mod

    original = mod.predict_with_phase
    mod.predict_with_phase = fake_predict
    try:
        report = evaluate_open_loop(
            model,
            env,
            None,
            human_frames,
            _ACTIONS,
            attack_window=(1034, 1040),
            attack_table_frames=(1034, 1038),
        )
    finally:
        mod.predict_with_phase = original

    assert report.stats.total == 2
    assert report.stats.correct == 2
    assert len(report.attack_rows) == 2


def test_evaluate_open_loop_replay_frames_scores_decision_only() -> None:
    decision = [
        FrameAction(frame=1034, action="", action_index=0),
        FrameAction(frame=1038, action="right", action_index=1),
    ]
    replay = [
        FrameAction(frame=1034, action="", action_index=0),
        FrameAction(frame=1035, action="", action_index=0),
        FrameAction(frame=1036, action="", action_index=0),
        FrameAction(frame=1037, action="", action_index=0),
        FrameAction(frame=1038, action="right", action_index=1),
    ]
    env = MagicMock()
    env.reset.return_value = (
        np.zeros((4, 84, 84), dtype=np.float32),
        {"ram": {"frame": 1034}, "phase_id": "gameplay"},
    )
    env.step.side_effect = [
        (np.zeros((4, 84, 84), dtype=np.float32), 0.0, False, False, {"ram": {"frame": 1035}, "phase_id": "gameplay"}),
        (np.zeros((4, 84, 84), dtype=np.float32), 0.0, False, False, {"ram": {"frame": 1036}, "phase_id": "gameplay"}),
        (np.zeros((4, 84, 84), dtype=np.float32), 0.0, False, False, {"ram": {"frame": 1037}, "phase_id": "gameplay"}),
        (np.zeros((4, 84, 84), dtype=np.float32), 0.0, False, False, {"ram": {"frame": 1038}, "phase_id": "gameplay"}),
        (np.zeros((4, 84, 84), dtype=np.float32), 0.0, False, False, {"ram": {"frame": 1039}, "phase_id": "gameplay"}),
    ]

    model = MagicMock()
    model.predict.side_effect = [(np.array([0]), None), (np.array([1]), None)]

    def fake_predict(model, obs, phase_id, heads_spec, deterministic=True):
        action, state = model.predict(obs, deterministic=deterministic)
        return action, state, "gameplay"

    import bc_open_loop_eval as mod

    original = mod.predict_with_phase
    mod.predict_with_phase = fake_predict
    try:
        report = evaluate_open_loop(
            model,
            env,
            None,
            decision,
            _ACTIONS,
            replay_frames=replay,
            attack_window=(1034, 1040),
            attack_table_frames=(1034, 1038),
        )
    finally:
        mod.predict_with_phase = original

    assert report.stats.total == 2
    assert report.stats.correct == 2
    assert env.step.call_count == 5


def test_parse_attack_window() -> None:
    assert parse_attack_window("1195-1210") == (1195, 1210)
    with pytest.raises(ValueError):
        parse_attack_window("1210-1195")


def test_resolve_save_state_start_frame_m1() -> None:
    from bc_open_loop_eval import resolve_save_state_start_frame
    from project_paths import mission_dir

    mission = mission_dir("rushn_attack", "m1")
    assert resolve_save_state_start_frame(mission, "save_states/cp_gameplay0.fc0") == 1034
