"""Unit: BC head resolution и загрузка NPZ."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from train.bc_pretrain import (
    checkpoint_id_from_save_rel,
    checkpoint_id_to_head_map,
    load_demo_dataset,
    resolve_bc_head_id,
)
from train.phase_heads import load_policy_heads_spec
from obs_contract import OBS_SHAPE

_SAMPLE_HEAD_SAVE_STATES = {
    "title": [{"id": "cp_title0", "frame": 20, "label": "title_screen"}],
    "gameplay": [
        {"id": "cp_gameplay0", "frame": 1243, "label": "level_start"},
        {"id": "cp_gameplay1", "frame": 1506, "label": "after_second_ladder"},
    ],
}


def test_checkpoint_id_from_save_rel() -> None:
    assert checkpoint_id_from_save_rel("save_states/cp_gameplay0.fc0") == "cp_gameplay0"


def test_resolve_bc_head_from_segment_save_state() -> None:
    heads = load_policy_heads_spec("rushn_attack")
    assert heads is not None
    seg = {
        "id": "seg_002",
        "frame_start": 1243,
        "save_state": "save_states/cp_gameplay0.fc0",
    }
    assert (
        resolve_bc_head_id(
            seg, head_save_states=_SAMPLE_HEAD_SAVE_STATES, heads_spec=heads
        )
        == "gameplay"
    )


def test_resolve_bc_head_title_segment() -> None:
    heads = load_policy_heads_spec("rushn_attack")
    assert heads is not None
    seg = {
        "id": "seg_001",
        "frame_start": 1,
        "save_state": "save_states/cp_title0.fc0",
    }
    assert (
        resolve_bc_head_id(seg, head_save_states=_SAMPLE_HEAD_SAVE_STATES, heads_spec=heads)
        == "title"
    )


def test_resolve_bc_head_explicit_bc_head() -> None:
    heads = load_policy_heads_spec("rushn_attack")
    assert heads is not None
    seg = {"id": "x", "bc_head": "bossfight"}
    assert resolve_bc_head_id(seg, head_save_states=None, heads_spec=heads) == "bossfight"


def test_resolve_bc_head_unknown_bc_head_raises() -> None:
    heads = load_policy_heads_spec("rushn_attack")
    assert heads is not None
    with pytest.raises(ValueError, match="bc_head"):
        resolve_bc_head_id({"id": "x", "bc_head": "nope"}, head_save_states=None, heads_spec=heads)


def test_checkpoint_id_to_head_map_nonempty() -> None:
    m = checkpoint_id_to_head_map(_SAMPLE_HEAD_SAVE_STATES)
    assert m.get("cp_gameplay0") == "gameplay"
    assert m.get("cp_title0") == "title"


def test_load_demo_dataset_uses_npz_actions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("project_paths.repo_root", lambda: tmp_path)
    game_id = "rushn_attack"
    mission = tmp_path / "games" / game_id / "missions" / "m1"
    demos = mission / "reference" / "demos_for_bc"
    demos.mkdir(parents=True)
    config = mission / "config"
    config.mkdir(parents=True)
    (config / "playthrough_manifest.yaml").write_text(
        "segments:\n  - id: seg_001\n    frame_start: 10\n    frame_end: 18\n",
        encoding="utf-8",
    )

    obs = np.zeros((2, *OBS_SHAPE), dtype=np.float32)
    obs[:, -1, :, :] = 0.5
    obs[:, -1, 40:50, 20:60] = 0.9
    actions = np.array([1, 2], dtype=np.int64)
    meta = json.dumps(
        {
            "segment_id": "seg_001",
            "frame_start": 10,
            "frame_end": 18,
            "record_mode": "fm2_playmovie",
        }
    )
    np.savez_compressed(demos / "seg_001.npz", obs=obs, actions=actions, meta=np.array(meta))

    batch = load_demo_dataset(mission, require_quality_pass=True)
    assert batch is not None
    assert batch.obs.shape[0] == 2
    assert list(batch.actions) == [1, 2]
