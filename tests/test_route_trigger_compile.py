"""Тесты compile route_triggers из anchor + scout."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from route_trigger_compile import (
    assert_routes_ready_for_compile,
    compile_triggers_for_anchors,
    list_route_anchors,
    write_route_triggers,
)


def _minimal_ram_hex(room_addr: int, room_val: int, stage_addr: int, stage_val: int) -> str:
    raw = bytearray(0x800)
    raw[room_addr] = room_val
    raw[stage_addr] = stage_val
    return raw.hex()


def test_compile_triggers_for_anchors() -> None:
    addrs = {"room": 0x0C, "stage": 0x30}
    frames = [
        {
            "frame": 100,
            "ram_hex": _minimal_ram_hex(0x0C, 0x00, 0x30, 1),
            "input": "",
        }
    ]
    compile_config = {
        "fields": {
            "room": {"mode": "exact"},
            "stage": {"mode": "min_threshold"},
        }
    }
    triggers = compile_triggers_for_anchors(
        anchors=["cp_gameplay1"],
        anchor_frames={"cp_gameplay1": 100},
        frames=frames,
        addrs=addrs,
        compile_config=compile_config,
    )
    assert triggers["cp_gameplay1"] == {"room": "0x00", "min_stage": 1}


def test_compile_min_floor_raises_stage_threshold() -> None:
    addrs = {"room": 0x0C, "stage": 0x30}
    frames = [
        {
            "frame": 1780,
            "ram_hex": _minimal_ram_hex(0x0C, 0x00, 0x30, 0),
            "input": "",
        }
    ]
    compile_config = {
        "fields": {
            "room": {"mode": "exact"},
            "stage": {"mode": "min_threshold", "min_floor": 1},
        }
    }
    triggers = compile_triggers_for_anchors(
        anchors=["cp_gameplay1"],
        anchor_frames={"cp_gameplay1": 1780},
        frames=frames,
        addrs=addrs,
        compile_config=compile_config,
    )
    assert triggers["cp_gameplay1"] == {"room": "0x00", "min_stage": 1}


def test_validate_routes_collects_anchors() -> None:
    routes = {
        "checkpoints": [
            {"id": 1, "name": "a", "anchor": "cp_gameplay1"},
            {"id": 2, "name": "clear", "trigger": {"flag": "mission_complete"}},
        ]
    }
    assert list_route_anchors(routes) == ["cp_gameplay1"]


def test_assert_routes_rejects_inline_ram() -> None:
    routes = {"checkpoints": [{"id": 1, "trigger": {"room": "0x00", "min_stage": 1}}]}
    with pytest.raises(ValueError, match="inline RAM trigger"):
        assert_routes_ready_for_compile(routes)


def test_write_route_triggers(tmp_path: Path) -> None:
    mission = tmp_path / "m1"
    (mission / "config").mkdir(parents=True)
    out = write_route_triggers(
        mission,
        {"cp_gameplay1": {"room": "0x00", "min_stage": 1}},
        metadata={"fm2_file": "reference/clear.fm2"},
    )
    data = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert data["triggers"]["cp_gameplay1"]["min_stage"] == 1
