"""Unit tests for FM2 inference playlist (BACKLOG 3.6 / C3)."""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from achievements.playlist import (  # noqa: E402
    build_playlist,
    write_overlay_clip,
)
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


def _minimal_config() -> dict:
    return {
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


def test_build_playlist_fm2_manifest() -> None:
    logs = repo_root() / "tmp" / "smoke" / "playlist_fm2" / "logs"
    if logs.exists():
        shutil.rmtree(logs)
    logs.mkdir(parents=True)
    inputs = logs / "20260716_inference_inputs.jsonl"
    inputs.write_text(
        "\n".join(
            json.dumps({"episode": 1, "step": i, "frame": i, "action": "right"})
            for i in range(4)
        )
        + "\n",
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
    created, manifest_path, clip_count = build_playlist(
        attempts,
        logs,
        config=_minimal_config(),
        inference_inputs_path=inputs,
        game="rushn_attack",
        mission="m1",
    )
    assert clip_count == 1
    assert manifest_path and manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    clip = manifest["clips"][0]
    assert clip["episode"] == 1
    assert clip["fm2"].endswith(".fm2")
    assert "inference_inputs" not in clip
    fm2 = logs / clip["fm2"]
    assert fm2.is_file()
    assert "savestate " in fm2.read_text(encoding="utf-8", errors="replace")
    overlay = logs / clip["overlay"]
    assert overlay.is_file()
    assert "save_state" not in json.loads(overlay.read_text(encoding="utf-8"))
    launcher = manifest_path.with_suffix(".play.cmd")
    assert launcher.is_file()
    assert "play_inference_fm2.py" in launcher.read_text(encoding="utf-8")
    assert "--skip-preflight" in launcher.read_text(encoding="utf-8")
    assert created["episode_reward"][0] == fm2


def test_build_playlist_clones_conventional_ep_fm2() -> None:
    logs = repo_root() / "tmp" / "smoke" / "playlist_clone_ep" / "logs"
    if logs.exists():
        shutil.rmtree(logs)
    logs.mkdir(parents=True)
    src_ep = (
        repo_root()
        / "games"
        / "rushn_attack"
        / "missions"
        / "m1"
        / "logs"
        / "20260716_ep0001.fm2"
    )
    if not src_ep.is_file():
        return
    date_prefix = datetime.now(timezone.utc).strftime("%Y%m%d")
    ep_copy = logs / f"{date_prefix}_ep0001.fm2"
    shutil.copy2(src_ep, ep_copy)
    attempts = logs / f"{date_prefix}_attempts.jsonl"
    attempts.write_text(
        json.dumps(
            {
                "episode": 1,
                "episode_reward": 42.0,
                "episode_frames": 4,
                "max_checkpoint": 2,
                "died": False,
                "tags": ["episode_reward"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    _, manifest_path, clip_count = build_playlist(
        attempts,
        logs,
        config=_minimal_config(),
        game="rushn_attack",
        mission="m1",
    )
    assert clip_count == 1
    assert manifest_path
    clip = json.loads(manifest_path.read_text(encoding="utf-8"))["clips"][0]
    assert (logs / clip["fm2"]).is_file()
    assert clip["fm2"] != ep_copy.name


def test_build_playlist_dedupes_identical_fm2() -> None:
    logs = repo_root() / "tmp" / "smoke" / "playlist_dedupe_fm2" / "logs"
    if logs.exists():
        shutil.rmtree(logs)
    logs.mkdir(parents=True)
    inputs = logs / "inputs.jsonl"
    rows = []
    for ep in (1, 2, 3):
        for i in range(4):
            rows.append(json.dumps({"episode": ep, "step": i, "action": "right"}))
    inputs.write_text("\n".join(rows) + "\n", encoding="utf-8")
    attempts = logs / "attempts.jsonl"
    attempt_rows = [
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
    attempts.write_text("\n".join(json.dumps(r) for r in attempt_rows) + "\n", encoding="utf-8")
    _, manifest_path, clip_count = build_playlist(
        attempts,
        logs,
        config=_minimal_config(),
        inference_inputs_path=inputs,
        dedupe=True,
    )
    assert clip_count == 1
    assert manifest_path
    assert len(json.loads(manifest_path.read_text(encoding="utf-8"))["clips"]) == 1
