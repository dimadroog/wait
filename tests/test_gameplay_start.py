"""Unit tests for Phase 0 config and gameplay start (Strategy in plugin YAML)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from phase0_config import (  # noqa: E402
    load_phase0_config,
    transition_rooms_from_config,
)
from playthrough_build import (  # noqa: E402
    gameplay_start_frame_from_rows,
    load_human_playthrough_rows,
)


def test_phase0_config_rushn_attack() -> None:
    phase0 = load_phase0_config("rushn_attack")
    rooms = transition_rooms_from_config(phase0)
    assert 0xFF in rooms
    assert 0x00 not in rooms
    assert phase0.get("segment_count") == 5
    assert len(phase0.get("checkpoint_heuristics", [])) >= 1


def test_gameplay_start_frame_m1() -> None:
    mission = Path(__file__).resolve().parents[1] / "games" / "rushn_attack" / "missions" / "m1"
    phase0 = load_phase0_config("rushn_attack")
    rows = load_human_playthrough_rows(mission / "reference" / "human_playthrough.jsonl")
    frame = gameplay_start_frame_from_rows(
        rows, transition_rooms=transition_rooms_from_config(phase0)
    )
    assert frame == 18
    start = rows[frame - 1]
    assert start["room"] == "0x00"
