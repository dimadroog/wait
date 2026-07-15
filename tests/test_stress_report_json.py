"""Unit tests for stress report JSON payload (FAIL_REPORT R0.3)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from stress_e2e_gate import PhaseResult, StressReport, _stress_phase_record, build_stress_report_payload


def test_stress_phase_record_bridge_failure() -> None:
    result = PhaseResult(
        name="bridge_parallel",
        ok=False,
        elapsed_s=72.5,
        error="rank 2: FceuxBridgeError('IPC timeout for STEP (30.0s)')",
        detail={
            "n_envs": 8,
            "failures": [{"rank": 2, "error": "FceuxBridgeError('IPC timeout for STEP (30.0s)')"}],
        },
    )
    record = _stress_phase_record(result)
    assert record["phase"] == "bridge_parallel"
    assert record["rank"] == 2
    assert record["wall_s"] == 72.5
    assert record["error"] is not None
    assert record["detail"]["failures"][0]["rank"] == 2


def test_build_stress_report_payload() -> None:
    report = StressReport(
        mode="full",
        n_envs=8,
        cycles_per_rollout=128,
        bridge_steps=128,
        wall_s=468.85,
        preflight_orphans_before=0,
        phases=[
            PhaseResult(
                name="vec_rollout_2",
                ok=True,
                elapsed_s=143.87,
                detail={"auto_dones": 512, "cycles": 128},
            )
        ],
    )
    payload = build_stress_report_payload(report, game="rushn_attack", mission="m1")
    assert payload["schema_version"] == 1
    assert payload["kind"] == "stress_e2e_gate"
    assert payload["phases"][0]["auto_dones"] == 512
    assert payload["phases"][0]["wall_s"] == 143.87
