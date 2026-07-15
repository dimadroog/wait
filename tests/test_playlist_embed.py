"""Unit tests for playlist self-contained FM2 (BACKLOG 3.2–3.3)."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from achievements.playlist import (  # noqa: E402
    _copy_overlay_sidecar,
    build_playlist,
)
from fm2_export import export_episode_fm2_from_steps, fm2_has_embedded_savestate  # noqa: E402
from project_paths import repo_root  # noqa: E402

_MISSION = Path(__file__).resolve().parents[1] / "games" / "rushn_attack" / "missions" / "m1"
_INFERENCE_CP0 = _MISSION / "states" / "inference_cp0.fc0"


@pytest.fixture
def inference_cp0() -> Path:
    if not _INFERENCE_CP0.is_file():
        pytest.skip(f"missing {_INFERENCE_CP0}")
    return _INFERENCE_CP0


def _make_embedded_fm2(path: Path, inference_cp0: Path) -> Path:
    export_episode_fm2_from_steps(
        [{"action": "right"}],
        path,
        save_state_path=inference_cp0,
    )
    assert fm2_has_embedded_savestate(path)
    return path


def test_copy_overlay_sidecar_writes_from_record(tmp_path: Path, inference_cp0: Path) -> None:
    src = _make_embedded_fm2(tmp_path / "src.fm2", inference_cp0)
    dest = tmp_path / "dest.fm2"
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    record = {
        "episode_reward": 10.0,
        "max_checkpoint": 2,
        "episode_frames": 100,
        "tags": ["episode_reward"],
    }
    config = {"nominations": [{"slug": "episode_reward", "idx": 2, "title": "x"}]}
    out = _copy_overlay_sidecar(
        src,
        dest,
        record=record,
        config=config,
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert "save_state" not in payload
    assert payload.get("stats", {}).get("max_cp") == 2


def test_build_playlist_embedded_manifest(inference_cp0: Path) -> None:
    logs = repo_root() / "tmp" / "smoke" / "playlist_embed" / "logs"
    if logs.exists():
        import shutil

        shutil.rmtree(logs)
    logs.mkdir(parents=True)
    ep_fm2 = _make_embedded_fm2(logs / "20260710_ep0001.fm2", inference_cp0)
    attempts = logs / "20260710_attempts.jsonl"
    attempts.write_text(
        json.dumps(
            {
                "episode": 1,
                "episode_reward": 42.0,
                "episode_frames": 100,
                "max_checkpoint": 2,
                "died": False,
                "tags": ["episode_reward"],
                "fm2_path": str(ep_fm2.resolve()),
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
        game="rushn_attack",
        mission="m1",
    )
    assert clip_count == 1
    assert manifest_path and manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    clip = manifest["clips"][0]
    assert "save_state" not in clip
    dest_fm2 = logs / clip["fm2"]
    assert dest_fm2.is_file()
    assert fm2_has_embedded_savestate(dest_fm2)
    overlay = logs / clip["overlay"]
    assert overlay.is_file()
    assert "save_state" not in json.loads(overlay.read_text(encoding="utf-8"))
    assert manifest_path.with_suffix(".play.cmd").is_file()
    assert created["episode_reward"][0] == dest_fm2


def test_build_playlist_dedupes_identical_fm2(inference_cp0: Path) -> None:
    logs = repo_root() / "tmp" / "smoke" / "playlist_dedupe" / "logs"
    if logs.exists():
        import shutil

        shutil.rmtree(logs)
    logs.mkdir(parents=True)
    ep_fm2 = _make_embedded_fm2(logs / "ep1.fm2", inference_cp0)
    attempts = logs / "attempts.jsonl"
    rows = [
        {
            "episode": i,
            "episode_reward": float(100 - i),
            "episode_frames": 100,
            "max_checkpoint": 2,
            "died": False,
            "tags": ["episode_reward"],
            "fm2_path": str(ep_fm2.resolve()),
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        for i in range(3)
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
        dedupe=True,
    )
    assert clip_count == 1
    assert manifest_path
    assert len(json.loads(manifest_path.read_text(encoding="utf-8"))["clips"]) == 1

