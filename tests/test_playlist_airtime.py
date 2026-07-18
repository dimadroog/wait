"""Формула airtime: Σ (fm2_frames + hold) / 60."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from achievements.airtime import (  # noqa: E402
    DEFAULT_HOLD_FRAMES,
    NES_FPS,
    estimate_clip_airtime_seconds,
    estimate_fm2_frames,
    frames_to_seconds,
    measure_playlist_airtime,
    overlay_hold_frames,
)
from achievements.playlist import write_playlist_manifest  # noqa: E402


def _write_fm2(path: Path, n_frames: int) -> None:
    header = "version 3\nemulatorVersion 22020\nromFilename game.nes\n"
    body = "".join(f"|0|........|\n" for _ in range(n_frames))
    path.write_text(header + body, encoding="utf-8")


def test_estimate_fm2_frames_and_seconds() -> None:
    assert estimate_fm2_frames(10, frame_skip=4) == 40
    assert frames_to_seconds(60) == 1.0
    # 10 env-steps × 4 + hold 180 → 220 / 60
    assert estimate_clip_airtime_seconds(10) == (40 + DEFAULT_HOLD_FRAMES) / NES_FPS


def test_overlay_hold_frames_from_show_until(tmp_path: Path) -> None:
    overlay = tmp_path / "c.overlay.json"
    overlay.write_text(json.dumps({"show_until_frame": 240}), encoding="utf-8")
    assert overlay_hold_frames(overlay) == 240
    assert overlay_hold_frames(None) == DEFAULT_HOLD_FRAMES


def test_measure_playlist_airtime_sums_fm2_and_hold(tmp_path: Path) -> None:
    day = tmp_path / "20260718"
    day.mkdir()
    _write_fm2(day / "01_a_001.fm2", 60)
    _write_fm2(day / "02_b_001.fm2", 120)
    (day / "01_a_001.overlay.json").write_text(
        json.dumps({"show_until_frame": 180}), encoding="utf-8"
    )
    (day / "02_b_001.overlay.json").write_text(
        json.dumps({"show_until_frame": 60}), encoding="utf-8"
    )
    playlist = {
        "date": "20260718",
        "clips": [
            {"fm2": "01_a_001.fm2", "overlay": "01_a_001.overlay.json"},
            {"fm2": "02_b_001.fm2", "overlay": "02_b_001.overlay.json"},
        ],
    }
    air = measure_playlist_airtime(playlist, logs_dir=day)
    assert air.clip_count == 2
    assert air.total_fm2_frames == 180
    assert air.total_hold_frames == 240
    assert air.total_frames == 420
    assert air.seconds == 420 / 60.0
    assert air.hours == air.seconds / 3600.0


def test_write_playlist_manifest_embeds_airtime(tmp_path: Path) -> None:
    day = tmp_path / "20260718"
    day.mkdir()
    _write_fm2(day / "01_x_001.fm2", 30)
    (day / "01_x_001.overlay.json").write_text(
        json.dumps({"show_until_frame": 90}), encoding="utf-8"
    )
    clips = [{"idx": 1, "fm2": "01_x_001.fm2", "overlay": "01_x_001.overlay.json"}]
    path = write_playlist_manifest(clips, day, date_prefix="20260718")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["airtime"]["clip_count"] == 1
    assert data["airtime"]["total_fm2_frames"] == 30
    assert data["airtime"]["total_hold_frames"] == 90
    assert data["airtime"]["seconds"] == 2.0  # (30+90)/60
