"""Триггеры CP из routes.yaml (в т.ч. requires_checkpoint)."""
from __future__ import annotations

from rewards.checkpoint_wrapper import trigger_matches


def test_trigger_room_and_min_y() -> None:
    assert trigger_matches({"room": "0x00", "min_y": 60}, {"room": "0x00", "y": 60})
    assert not trigger_matches({"room": "0x00", "min_y": 60}, {"room": "0x00", "y": 10})


def test_requires_checkpoint_blocks_until_prior() -> None:
    trig = {"room": "0x00", "min_y": 60, "requires_checkpoint": 3}
    ram = {"room": "0x00", "y": 80}
    assert not trigger_matches(trig, ram, achieved=set())
    assert not trigger_matches(trig, ram, achieved={1, 2})
    assert trigger_matches(trig, ram, achieved={1, 2, 3})


def test_start_room_alone_is_not_late_cp() -> None:
    """H3: mid_mission ещё нет → late 0x00+min_y не срабатывает."""
    trig = {"room": "0x00", "min_y": 60, "requires_checkpoint": 3}
    assert not trigger_matches(trig, {"room": "0x00", "y": 135}, achieved={})
