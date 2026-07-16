"""Unit tests for etalon build config and gameplay start (Strategy in plugin YAML)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from etalon_build_config import (  # noqa: E402
    load_etalon_build_config,
    transition_rooms_from_etalon_build,
)
from playthrough_build import (  # noqa: E402
    gameplay_start_frame_from_rows,
    load_human_playthrough_rows,
)


def test_etalon_build_config_rushn_attack() -> None:
    etalon_build = load_etalon_build_config("rushn_attack")
    rooms = transition_rooms_from_etalon_build(etalon_build)
    assert 0xFF in rooms
    assert 0x00 not in rooms
    assert etalon_build.get("segment_count") == 5
    assert len(etalon_build.get("checkpoint_heuristics", [])) >= 1


def test_gameplay_start_frame_m1() -> None:
    mission = Path(__file__).resolve().parents[1] / "games" / "rushn_attack" / "missions" / "m1"
    etalon_build = load_etalon_build_config("rushn_attack")
    rows = load_human_playthrough_rows(mission / "reference" / "human_playthrough.jsonl")
    frame = gameplay_start_frame_from_rows(
        rows, transition_rooms=transition_rooms_from_etalon_build(etalon_build)
    )
    # Not frame 18 (title) or 1226 (fade): need lives + movement input → 1250.
    assert frame == 1250
    start = rows[frame - 1]
    assert 1 <= int(start["lives"]) <= 9
    assert "right" in str(start.get("action", "")).lower()
    assert int(str(start["room"]), 16) not in transition_rooms_from_etalon_build(
        etalon_build
    )
