"""Unit tests for session JSON reports (FAIL_REPORT R0.3)."""
from __future__ import annotations

from train.session_report import (
    parse_failure_rank,
    phase_record,
    rollout_phase_records,
)


def test_parse_failure_rank_from_train_session() -> None:
    error = "FceuxBridgeError: IPC timeout for STEP (30.0s) in train_5"
    assert parse_failure_rank(error) == 5


def test_phase_record_fields() -> None:
    record = phase_record(
        phase="vec_rollout_1",
        ok=True,
        wall_s=203.896,
        auto_dones=512,
        detail={"cycles": 128},
    )
    assert record["phase"] == "vec_rollout_1"
    assert record["wall_s"] == 203.9
    assert record["auto_dones"] == 512
    assert record["error"] is None
    assert record["rank"] is None


def test_rollout_phase_records_with_failure() -> None:
    phases = rollout_phase_records(
        rollout_wall_s=[214.2],
        rollout_auto_dones=[512],
        learn_error="BrokenPipeError rank 3 train_3",
    )
    assert len(phases) == 2
    assert phases[0]["ok"] is True
    assert phases[0]["auto_dones"] == 512
    assert phases[1]["ok"] is False
    assert phases[1]["phase"] == "rollout_2"
    assert phases[1]["rank"] == 3
