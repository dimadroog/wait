"""load_demo_dataset: prefer_embedded_actions для ablation-фильтров."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from train.bc_pretrain import load_demo_dataset


def test_prefer_embedded_actions(tmp_path: Path) -> None:
    obs = np.zeros((3, 4, 84, 84), dtype=np.float32)
    actions = np.asarray([2, 2, 1], dtype=np.int64)
    meta = {
        "segment_id": "h4_test",
        "obs_stub": False,
        "prefer_embedded_actions": True,
        # wrong range on purpose — must NOT reload from jsonl
        "frame_start": 1,
        "frame_end": 1,
    }
    npz = tmp_path / "h4_test.npz"
    np.savez_compressed(npz, obs=obs, actions=actions, meta=np.asarray(json.dumps(meta)))

    # mission path only needed for jsonl fallback; empty mission dir is enough when embedded
    mission = tmp_path / "mission"
    (mission / "config").mkdir(parents=True)
    (mission / "config" / "playthrough_manifest.yaml").write_text("segments: []\n", encoding="utf-8")

    ds = load_demo_dataset(mission, demo_paths=[npz], require_real_obs=True)
    assert ds is not None
    out_obs, out_act = ds
    assert out_obs.shape == (3, 4, 84, 84)
    assert out_act.tolist() == [2, 2, 1]
