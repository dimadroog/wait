"""Триггеры CP из routes.yaml (в т.ч. requires_checkpoint)."""
from __future__ import annotations

from rewards.checkpoint_wrapper import trigger_matches


def test_trigger_room_and_min_y() -> None:
    assert trigger_matches({"room": "0x00", "min_y": 60}, {"room": "0x00", "y": 60})
    assert not trigger_matches({"room": "0x00", "min_y": 60}, {"room": "0x00", "y": 10})


def test_trigger_min_stage() -> None:
    assert trigger_matches({"room": "0x00", "min_stage": 3}, {"room": "0x00", "stage": 3})
    assert not trigger_matches({"room": "0x00", "min_stage": 3}, {"room": "0x00", "stage": 2})
    assert not trigger_matches({"room": "0x00", "min_stage": 1}, {"room": "0x00", "stage": 0})


def test_requires_checkpoint_blocks_until_prior() -> None:
    trig = {"room": "0x00", "min_stage": 8, "requires_checkpoint": 3}
    ram = {"room": "0x00", "stage": 8}
    assert not trigger_matches(trig, ram, achieved=set())
    assert not trigger_matches(trig, ram, achieved={1, 2})
    assert trigger_matches(trig, ram, achieved={1, 2, 3})


def test_start_stage_zero_is_not_paid_cp() -> None:
    """Старт cp_gameplay0 (stage=0) не даёт after_second_ladder."""
    trig = {"room": "0x00", "min_stage": 1}
    assert not trigger_matches(trig, {"room": "0x00", "stage": 0}, achieved=set())
