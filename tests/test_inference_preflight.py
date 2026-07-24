"""Unit tests for inference preflight (gen pool)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from inference_preflight import (  # noqa: E402
    cleanup_inference_logs,
    cleanup_play_fm2_staging,
    report_gen_airtime,
    require_inference_preflight,
    require_playback_preflight,
)


def test_cleanup_inference_logs_removes_gen_pool(tmp_path: Path) -> None:
    keep = tmp_path / ".gitkeep"
    keep.write_text("", encoding="utf-8")
    pool = tmp_path / "gen0"
    pool.mkdir()
    (pool / "attempts.jsonl").write_text("{}", encoding="utf-8")
    (pool / "ep0001.fm2").write_text("fm2", encoding="utf-8")
    other = tmp_path / "gen1"
    other.mkdir()
    (other / "attempts.jsonl").write_text("{}", encoding="utf-8")
    day_legacy = tmp_path / "20260724"
    day_legacy.mkdir()
    (day_legacy / "attempts.jsonl").write_text("{}", encoding="utf-8")

    removed = cleanup_inference_logs(tmp_path, model_version="gen0")

    assert pool in removed
    assert not pool.exists()
    assert other.is_dir()
    assert day_legacy.is_dir()
    assert keep.is_file()


def test_cleanup_play_fm2_staging(tmp_path: Path) -> None:
    staging = tmp_path / "tmp" / "play_fm2" / "staging"
    staging.mkdir(parents=True)
    (staging / "clip.fm2").write_text("x", encoding="utf-8")
    with patch("inference_preflight.repo_root", return_value=tmp_path):
        cleanup_play_fm2_staging()
    assert not staging.exists()


def test_require_inference_preflight_keeps_logs_by_default(tmp_path: Path, capsys) -> None:
    mission = tmp_path / "games" / "rushn_attack" / "missions" / "m1"
    logs = mission / "logs"
    pool = logs / "gen0"
    pool.mkdir(parents=True)
    kept = pool / "attempts.jsonl"
    kept.write_text("{}\n", encoding="utf-8")
    (mission / "models").mkdir(parents=True)
    (mission / "models" / "latest.zip").write_bytes(b"x")
    with patch("inference_preflight.repo_root", return_value=tmp_path):
        with patch("inference_preflight.mission_dir", return_value=mission):
            with patch("inference_preflight.require_clean_preflight") as require_clean:
                require_inference_preflight(model_version="gen0", label="test")
    assert kept.is_file()
    require_clean.assert_called_once()
    out = capsys.readouterr().out
    assert "keep gen logs" in out
    assert "airtime=0s" in out


def test_require_inference_preflight_wipe_gen_logs(tmp_path: Path) -> None:
    mission = tmp_path / "games" / "rushn_attack" / "missions" / "m1"
    logs = mission / "logs"
    pool = logs / "gen0"
    pool.mkdir(parents=True)
    stale = pool / "playlist.json"
    stale.write_text("{}", encoding="utf-8")
    with patch("inference_preflight.repo_root", return_value=tmp_path):
        with patch("inference_preflight.mission_dir", return_value=mission):
            with patch("inference_preflight.require_clean_preflight") as require_clean:
                require_inference_preflight(
                    model_version="gen0", clean_logs=True, label="test"
                )
    assert not pool.exists()
    require_clean.assert_called_once()


def test_report_gen_airtime_reads_playlist(tmp_path: Path, capsys) -> None:
    pool = tmp_path / "gen0"
    pool.mkdir()
    fm2 = pool / "01_x_001.fm2"
    fm2.write_text("version 3\n" + "".join("|0|........|\n" for _ in range(60)), encoding="utf-8")
    (pool / "01_x_001.overlay.json").write_text(
        json.dumps({"show_until_frame": 120}), encoding="utf-8"
    )
    (pool / "playlist.json").write_text(
        json.dumps({"clips": [{"fm2": "01_x_001.fm2", "overlay": "01_x_001.overlay.json"}]}),
        encoding="utf-8",
    )
    hours = report_gen_airtime(tmp_path, model_version="gen0", label="test")
    assert abs(hours - 3.0 / 3600.0) < 1e-9
    assert "airtime=3.0s" in capsys.readouterr().out


def test_require_playback_preflight_skips_log_wipe(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    pool = logs / "gen0"
    pool.mkdir(parents=True)
    log = pool / "attempts.jsonl"
    log.write_text("{}", encoding="utf-8")
    with patch("inference_preflight.require_clean_preflight") as require_clean:
        require_playback_preflight(label="test")
    assert log.is_file()
    require_clean.assert_called_once()


def test_require_inference_preflight_aborts_on_orphans(tmp_path: Path) -> None:
    mission = tmp_path / "games" / "x" / "missions" / "m1"
    (mission / "models").mkdir(parents=True)
    (mission / "models" / "latest.zip").write_bytes(b"x")
    with patch("inference_preflight.cleanup_play_fm2_staging"):
        with patch("inference_preflight.mission_dir", return_value=mission):
            with patch("inference_preflight.require_clean_preflight", side_effect=SystemExit(1)):
                with pytest.raises(SystemExit):
                    require_inference_preflight(clean_logs=False, model_version="latest")
