"""Unit tests for inference preflight."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from inference_preflight import (  # noqa: E402
    cleanup_inference_logs,
    cleanup_play_fm2_staging,
    require_inference_preflight,
    require_playback_preflight,
)
from jsonl_logs import utc_date_prefix  # noqa: E402


def test_cleanup_inference_logs_removes_dated_artifacts(tmp_path: Path) -> None:
    prefix = utc_date_prefix()
    keep = tmp_path / ".gitkeep"
    keep.write_text("", encoding="utf-8")
    day = tmp_path / prefix
    day.mkdir()
    (day / "attempts.jsonl").write_text("{}", encoding="utf-8")
    (day / "ep0001.fm2").write_text("fm2", encoding="utf-8")
    legacy = tmp_path / f"{prefix}_attempts.jsonl"
    legacy.write_text("{}", encoding="utf-8")
    other_day = tmp_path / "20260101"
    other_day.mkdir()
    (other_day / "attempts.jsonl").write_text("{}", encoding="utf-8")
    other_legacy = tmp_path / "20260101_attempts.jsonl"
    other_legacy.write_text("{}", encoding="utf-8")

    removed = cleanup_inference_logs(tmp_path, date_prefix=prefix)

    assert day in removed
    assert legacy in removed
    assert not day.exists()
    assert not legacy.exists()
    assert other_day.is_dir()
    assert other_legacy.is_file()
    assert keep.is_file()


def test_cleanup_play_fm2_staging(tmp_path: Path) -> None:
    staging = tmp_path / "tmp" / "play_fm2" / "staging"
    staging.mkdir(parents=True)
    (staging / "clip.fm2").write_text("x", encoding="utf-8")
    with patch("inference_preflight.repo_root", return_value=tmp_path):
        cleanup_play_fm2_staging()
    assert not staging.exists()


def test_require_inference_preflight_cleans_logs_and_bridge(tmp_path: Path) -> None:
    logs = tmp_path / "games" / "rushn_attack" / "missions" / "m1" / "logs"
    day = logs / utc_date_prefix()
    day.mkdir(parents=True)
    stale = day / "playlist.json"
    stale.write_text("{}", encoding="utf-8")
    with patch("inference_preflight.repo_root", return_value=tmp_path):
        with patch("inference_preflight.mission_dir", return_value=tmp_path / "games" / "rushn_attack" / "missions" / "m1"):
            with patch("inference_preflight.require_clean_preflight") as require_clean:
                require_inference_preflight(clean_logs=True, label="test")
    assert not day.exists()
    require_clean.assert_called_once()


def test_require_playback_preflight_skips_log_wipe(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    day = logs / utc_date_prefix()
    day.mkdir(parents=True)
    log = day / "attempts.jsonl"
    log.write_text("{}", encoding="utf-8")
    with patch("inference_preflight.require_clean_preflight") as require_clean:
        require_playback_preflight(label="test")
    assert log.is_file()
    require_clean.assert_called_once()


def test_require_inference_preflight_aborts_on_orphans() -> None:
    with patch("inference_preflight.cleanup_play_fm2_staging"):
        with patch("inference_preflight.require_clean_preflight", side_effect=SystemExit(1)):
            with pytest.raises(SystemExit):
                require_inference_preflight(clean_logs=False)
