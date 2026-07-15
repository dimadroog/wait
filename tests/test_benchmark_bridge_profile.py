"""Unit tests for benchmark_bridge ep_len2 profile (FAIL_REPORT R1.4)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from benchmark_bridge import EpLen2Profile, _gate_rollout_projection


def test_gate_rollout_projection_ep_len2() -> None:
    profile = EpLen2Profile(
        cycles=64,
        steps_total=128,
        resets_total=64,
        step_ms_mean=20.0,
        reset_ms_mean=80.0,
        step_wall_ms=2560.0,
        reset_wall_ms=5120.0,
        step_share_pct=33.3,
        reset_share_pct=66.7,
        cycle_ms_mean=120.0,
    )
    projection = _gate_rollout_projection(profile, vec_cycles=128, n_envs=8, ep_len=2)
    assert projection["env_steps_per_rollout"] == 1024
    assert projection["resets_per_rollout"] == 512
    assert projection["parallel_step_wall_s_est"] == 2.56
    assert projection["reset_wall_s_serial_est"] == 40.96
    assert projection["rollout_wall_s_est_low"] == projection["parallel_step_wall_s_est"] + projection["reset_wall_s_spread_est"]
