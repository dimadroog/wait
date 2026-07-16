"""Unit tests for inference playlist (BACKLOG 3.4)."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from achievements.playlist import (  # noqa: E402
    build_playlist,
    write_overlay_clip,
)
from inference_replay import episode_action_digest  # noqa: E402
from project_paths import repo_root  # noqa: E402


def test_write_overlay_clip_no_save_state(tmp_path: Path) -> None:
    dest = tmp_path / "clip.overlay.json"
    record = {
        "episode_reward": 10.0,
        "max_checkpoint": 2,
        "episode_frames": 100,
        "tags": ["episode_reward"],
    }
    config = {"nominations": [{"slug": "episode_reward", "idx": 2, "title": "x"}]}
    out = write_overlay_clip(dest, record=record, config=config)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert "save_state" not in payload
    assert payload.get("stats", {}).get("max_cp") == 2


def test_build_playlist_jsonl_manifest() -> None:
    logs = repo_root() / "tmp" / "smoke" / "playlist_jsonl" / "logs"
    if logs.exists():
        import shutil

        shutil.rmtree(logs)
    logs.mkdir(parents=True)
    inputs = logs / "20260716_inference_inputs.jsonl"
    inputs.write_text(
        json.dumps({"episode": 1, "step": 0, "frame": 0, "action": "right"}) + "\n",
        encoding="utf-8",
    )
    attempts = logs / "20260716_attempts.jsonl"
    attempts.write_text(
        json.dumps(
            {
                "episode": 1,
                "episode_reward": 42.0,
                "episode_frames": 4,
                "max_checkpoint": 2,
                "died": False,
                "tags": ["episode_reward"],
                "inference_inputs_ref": inputs.name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    config = {
        "broadcast_order": ["episode_reward"],
        "nominations": [
            {
                "idx": 2,
                "slug": "episode_reward",
                "title": "Greedy",
                "label": "Greedy",
                "tier": "gold",
                "type": "top_k",
                "field": "episode_reward",
                "k": 3,
                "order": "desc",
            }
        ],
    }
    created, manifest_path, clip_count = build_playlist(
        attempts,
        logs,
        config=config,
        inference_inputs_path=inputs,
        game="rushn_attack",
        mission="m1",
    )
    assert clip_count == 1
    assert manifest_path and manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    clip = manifest["clips"][0]
    assert clip["episode"] == 1
    assert clip["inference_inputs"] == inputs.name
    assert "fm2" not in clip
    overlay = logs / clip["overlay"]
    assert overlay.is_file()
    assert manifest_path.with_suffix(".play.cmd").is_file()
    assert created["episode_reward"][0] == overlay


def test_build_playlist_dedupes_identical_episode() -> None:
    logs = repo_root() / "tmp" / "smoke" / "playlist_dedupe_jsonl" / "logs"
    if logs.exists():
        import shutil

        shutil.rmtree(logs)
    logs.mkdir(parents=True)
    inputs = logs / "inputs.jsonl"
    inputs.write_text(
        json.dumps({"episode": 1, "action": "right"})
        + "\n"
        + json.dumps({"episode": 2, "action": "right"})
        + "\n",
        encoding="utf-8",
    )
    assert episode_action_digest(inputs, 1) == episode_action_digest(inputs, 2)
    attempts = logs / "attempts.jsonl"
    rows = [
        {
            "episode": i,
            "episode_reward": float(100 - i),
            "episode_frames": 4,
            "max_checkpoint": 2,
            "died": False,
            "tags": ["episode_reward"],
            "inference_inputs_ref": inputs.name,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        for i in range(1, 4)
    ]
    attempts.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    config = {
        "broadcast_order": ["episode_reward"],
        "nominations": [
            {
                "idx": 2,
                "slug": "episode_reward",
                "title": "Greedy",
                "label": "Greedy",
                "tier": "gold",
                "type": "top_k",
                "field": "episode_reward",
                "k": 3,
                "order": "desc",
            }
        ],
    }
    _, manifest_path, clip_count = build_playlist(
        attempts,
        logs,
        config=config,
        inference_inputs_path=inputs,
        dedupe=True,
    )
    assert clip_count == 1
    assert manifest_path
    assert len(json.loads(manifest_path.read_text(encoding="utf-8"))["clips"]) == 1
