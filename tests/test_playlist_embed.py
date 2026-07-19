"""Unit tests for FM2 inference playlist (BACKLOG 3.6 / C3)."""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from achievements.playlist import (  # noqa: E402
    DIED_ATTRACT_TAIL_FRAMES,
    DIED_TITLE_X_TAIL_FRAMES,
    TITLE_ATTRACT_X,
    build_playlist,
    write_overlay_clip,
)
from fm2_export import (  # noqa: E402
    build_empty_fm2,
    default_fm2_template,
    episode_fm2_guid,
    trim_fm2_tail_frames,
)
from jsonl_logs import utc_date_prefix  # noqa: E402
from project_paths import count_fm2_frames, mission_dir, repo_root  # noqa: E402


def test_trim_fm2_tail_frames(tmp_path: Path) -> None:
    mdir = mission_dir("rushn_attack", "m1")
    fc0 = mdir / "save_states" / "inference_cp0.fc0"
    if not fc0.is_file():
        return
    fm2 = tmp_path / "clip.fm2"
    build_empty_fm2(
        fm2,
        template=default_fm2_template("rushn_attack", "m1"),
        save_state_path=fc0,
        guid=episode_fm2_guid(salt="trim-test"),
        num_frames=300,
    )
    assert count_fm2_frames(fm2) == 300
    dropped = trim_fm2_tail_frames(fm2, 100, min_keep=60)
    assert dropped == 100
    assert count_fm2_frames(fm2) == 200


def test_build_playlist_trims_died_attract_tail() -> None:
    logs = repo_root() / "tmp" / "smoke" / "playlist_trim_died" / "logs"
    if logs.exists():
        shutil.rmtree(logs)
    day = logs / utc_date_prefix()
    day.mkdir(parents=True)
    n_steps = 400  # → 1600 FM2 frames; died without title-x → trim 900
    inputs = day / "inference_inputs.jsonl"
    inputs.write_text(
        "\n".join(
            json.dumps({"episode": 1, "step": i, "frame": i, "action": "right"})
            for i in range(n_steps)
        )
        + "\n",
        encoding="utf-8",
    )
    attempts = day / "attempts.jsonl"
    attempts.write_text(
        json.dumps(
            {
                "episode": 1,
                "episode_reward": 42.0,
                "episode_frames": n_steps,
                "max_checkpoint": 2,
                "died": True,
                "death_x": 50,
                "tags": ["episode_reward"],
                "inference_inputs_ref": inputs.name,
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
        inference_inputs_path=inputs,
        game="rushn_attack",
        mission="m1",
    )
    assert clip_count == 1
    assert manifest_path
    fm2 = day / json.loads(manifest_path.read_text(encoding="utf-8"))["clips"][0]["fm2"]
    full = n_steps * 4
    assert count_fm2_frames(fm2) == full - DIED_ATTRACT_TAIL_FRAMES


def test_build_playlist_trims_title_death_x_harder() -> None:
    logs = repo_root() / "tmp" / "smoke" / "playlist_trim_title_x" / "logs"
    if logs.exists():
        shutil.rmtree(logs)
    day = logs / utc_date_prefix()
    day.mkdir(parents=True)
    n_steps = 500  # → 2000 frames; death_x=129 → trim 1500 → 500
    inputs = day / "inference_inputs.jsonl"
    inputs.write_text(
        "\n".join(
            json.dumps({"episode": 1, "step": i, "frame": i, "action": "right"})
            for i in range(n_steps)
        )
        + "\n",
        encoding="utf-8",
    )
    attempts = day / "attempts.jsonl"
    attempts.write_text(
        json.dumps(
            {
                "episode": 1,
                "episode_reward": 42.0,
                "episode_frames": n_steps,
                "max_checkpoint": 2,
                "died": True,
                "death_x": TITLE_ATTRACT_X,
                "tags": ["episode_reward"],
                "inference_inputs_ref": inputs.name,
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
        inference_inputs_path=inputs,
        game="rushn_attack",
        mission="m1",
    )
    assert clip_count == 1
    assert manifest_path
    fm2 = day / json.loads(manifest_path.read_text(encoding="utf-8"))["clips"][0]["fm2"]
    assert count_fm2_frames(fm2) == n_steps * 4 - DIED_TITLE_X_TAIL_FRAMES


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
    day = logs / utc_date_prefix()
    day.mkdir(parents=True)
    inputs = day / "inference_inputs.jsonl"
    inputs.write_text(
        "\n".join(
            json.dumps({"episode": 1, "step": i, "frame": i, "action": "right"})
            for i in range(4)
        )
        + "\n",
        encoding="utf-8",
    )
    attempts = day / "attempts.jsonl"
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
    assert manifest_path.name == "playlist.json"
    assert manifest_path.parent == day
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    clip = manifest["clips"][0]
    assert clip["episode"] == 1
    assert clip["fm2"].endswith(".fm2")
    assert not clip["fm2"].startswith(utc_date_prefix())
    assert "inference_inputs" not in clip
    fm2 = day / clip["fm2"]
    assert fm2.is_file()
    assert "savestate " in fm2.read_text(encoding="utf-8", errors="replace")
    overlay = day / clip["overlay"]
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
    day = logs / utc_date_prefix()
    day.mkdir(parents=True)
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
        # fallback: any self-contained deep_run clip in flat or dated layout
        flat = list((repo_root() / "games" / "rushn_attack" / "missions" / "m1" / "logs").glob("*_ep0001.fm2"))
        dated = list(
            (repo_root() / "games" / "rushn_attack" / "missions" / "m1" / "logs").glob("*/ep0001.fm2")
        )
        candidates = flat + dated
        if not candidates:
            return
        src_ep = candidates[0]
    ep_copy = day / "ep0001.fm2"
    shutil.copy2(src_ep, ep_copy)
    attempts = day / "attempts.jsonl"
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
    assert (day / clip["fm2"]).is_file()
    assert clip["fm2"] != ep_copy.name
    assert not ep_copy.exists()  # raw ep cleaned after playlist build


def test_build_playlist_dedupes_identical_fm2() -> None:
    logs = repo_root() / "tmp" / "smoke" / "playlist_dedupe_fm2" / "logs"
    if logs.exists():
        shutil.rmtree(logs)
    day = logs / utc_date_prefix()
    day.mkdir(parents=True)
    inputs = day / "inputs.jsonl"
    rows = []
    for ep in (1, 2, 3):
        for i in range(4):
            rows.append(json.dumps({"episode": ep, "step": i, "action": "right"}))
    inputs.write_text("\n".join(rows) + "\n", encoding="utf-8")
    attempts = day / "attempts.jsonl"
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
