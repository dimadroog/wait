from pathlib import Path

from train.checkpointing import resolve_target_timesteps
from train.rollout_metrics import RolloutMetricsCallback, host_memory_mb


def test_resolve_target_raises_when_cli_higher() -> None:
    assert resolve_target_timesteps(100_000, {"target_timesteps": 20_000}) == 100_000


def test_resolve_target_keeps_sidecar_when_cli_lower() -> None:
    assert resolve_target_timesteps(10_000, {"target_timesteps": 20_000}) == 20_000


def test_resolve_target_without_sidecar() -> None:
    assert resolve_target_timesteps(50_000, None) == 50_000


def test_host_memory_mb_keys() -> None:
    mem = host_memory_mb()
    assert "avail_phys_mb" in mem
    assert "total_phys_mb" in mem
    assert "memory_load_pct" in mem


def test_rollout_metrics_writes_jsonl(tmp_path: Path) -> None:
    from unittest.mock import MagicMock

    path = tmp_path / "rollouts.jsonl"
    cb = RolloutMetricsCallback(path)
    model = MagicMock()
    model.num_timesteps = 0
    cb.model = model
    cb._on_training_start()
    model.num_timesteps = 768
    assert cb._on_rollout_end() is True
    model.num_timesteps = 1536
    assert cb._on_rollout_end() is True

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    import json

    row = json.loads(lines[1])
    assert row["rollout"] == 2
    assert row["delta_timesteps"] == 768
    assert row["wall_rollout_s"] >= 0
