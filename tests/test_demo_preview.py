"""Тесты demo_preview (экспорт PNG из seg_*.npz)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from demo_preview import export_all_demos, export_segment_preview, load_action_strings, quality_check_failures
from demo_quality import evaluate_segment_quality
from obs_contract import OBS_SHAPE


@pytest.fixture
def mission_with_demo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr("project_paths.repo_root", lambda: tmp_path)
    monkeypatch.setattr("demo_preview.repo_root", lambda: tmp_path)
    game_id = "rushn_attack"
    mission = tmp_path / "games" / game_id / "missions" / "m1"
    demos = mission / "reference" / "demos_for_bc"
    demos.mkdir(parents=True)
    meta = json.dumps(
        {
            "segment_id": "seg_001",
            "mission": "m1",
            "frame_start": 100,
            "frame_end": 200,
            "frame_skip": 4,
            "record_mode": "fm2_playmovie",
        }
    )
    obs = np.linspace(0.1, 0.9, 30 * int(np.prod(OBS_SHAPE)), dtype=np.float32).reshape(30, *OBS_SHAPE)
    obs[:, -1, 40:50, 20:60] = 0.9
    actions = np.arange(30, dtype=np.int64) % 3
    np.savez_compressed(demos / "seg_001.npz", obs=obs, actions=actions, meta=np.array(meta))

    env_cfg = tmp_path / "games" / game_id / "env_config.yaml"
    env_cfg.parent.mkdir(parents=True, exist_ok=True)
    env_cfg.write_text("actions: ['', 'left', 'right']\n", encoding="utf-8")

    return mission


def test_export_segment_preview_writes_grid_and_samples(mission_with_demo: Path) -> None:
    obs = np.linspace(0.1, 0.9, 30 * int(np.prod(OBS_SHAPE)), dtype=np.float32).reshape(30, *OBS_SHAPE)
    obs[:, -1, 40:50, 20:60] = 0.9
    quality = evaluate_segment_quality(obs, segment_id="seg_001", frame_start=100, gameplay_start_frame=None)
    out = mission_with_demo / "preview_out"
    result = export_segment_preview(
        mission_with_demo / "reference" / "demos_for_bc" / "seg_001.npz",
        out,
        action_strings=["", "left", "right"],
        quality=quality,
        step_interval=10,
        max_samples=30,
        grid_cols=5,
    )
    assert result.n_steps == 30
    assert result.quality.passed
    assert result.grid_path is not None
    assert result.grid_path.is_file()
    assert len(result.sample_paths) == 3
    assert all(p.is_file() for p in result.sample_paths)


def test_export_all_demos_index(mission_with_demo: Path) -> None:
    root, results = export_all_demos(
        mission_with_demo,
        "rushn_attack",
        out_dir=mission_with_demo / "tmp_out",
    )
    assert len(results) == 1
    index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    assert index["segments"][0]["id"] == "seg_001"
    assert "quality_passed" in index["segments"][0]
    assert (root / "seg_001" / "grid.png").is_file()


def test_quality_check_failures() -> None:
    from demo_preview import PreviewResult
    from demo_quality import DemoQualityMetrics, SegmentQualityResult

    bad = PreviewResult(
        segment_id="seg_x",
        npz_path=Path("x.npz"),
        out_dir=Path("out"),
        n_steps=1,
        obs_max=0.0,
        quality=SegmentQualityResult(
            segment_id="seg_x",
            metrics=DemoQualityMetrics(1, 1.0, 0.0, 0.0, 0.0),
            require_gameplay=True,
        ),
        grid_path=None,
        sample_paths=[],
    )
    assert quality_check_failures([bad])
