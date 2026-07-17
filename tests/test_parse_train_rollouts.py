import importlib.util
from pathlib import Path


def test_summarize_detects_degradation() -> None:
    spec = importlib.util.spec_from_file_location(
        "parse_train_rollouts",
        Path(__file__).resolve().parents[1] / "scripts" / "parse_train_rollouts.py",
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    rows = []
    for i in range(12):
        wall = 100.0 if i < 6 else 400.0
        rows.append(
            {
                "rollout": i + 1,
                "wall_rollout_s": wall,
                "env_steps_per_s": 768 / wall,
                "avail_phys_mb": 4000.0 - i * 10,
            }
        )
    summary = mod.summarize(rows)
    assert summary["n_rollouts"] == 12
    assert summary["degraded"] is True
    assert summary["wall_late_over_early"] >= 2.0


def test_summarize_stable() -> None:
    spec = importlib.util.spec_from_file_location(
        "parse_train_rollouts",
        Path(__file__).resolve().parents[1] / "scripts" / "parse_train_rollouts.py",
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    rows = [
        {"rollout": i + 1, "wall_rollout_s": 95.0 + (i % 3), "env_steps_per_s": 8.0}
        for i in range(12)
    ]
    summary = mod.summarize(rows)
    assert summary["degraded"] is False
