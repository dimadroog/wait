"""Контракт broadcast_board: агрегаты genN и дельта vs genN−1."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stream.broadcast_board import (  # noqa: E402
    aggregate_attempts,
    build_broadcast_board,
    delta_aggregates,
    prev_model_version,
)


def test_prev_model_version() -> None:
    assert prev_model_version("gen0") is None
    assert prev_model_version("gen1") == "gen0"
    assert prev_model_version("gen12.zip") == "gen11"


def test_aggregate_and_delta_reach_cp_and_wall() -> None:
    curr = [
        {"max_checkpoint": 2, "died": True, "death_room": "0x06", "death_x": 160, "mission_clear": False},
        {"max_checkpoint": 2, "died": True, "death_room": "0x06", "death_x": 161, "mission_clear": False},
        {"max_checkpoint": 3, "died": False, "mission_clear": False},
        {"max_checkpoint": 1, "died": True, "death_room": "0x08", "death_x": 10, "mission_clear": False},
    ]
    prev = [
        {"max_checkpoint": 1, "died": True, "death_room": "0x06", "death_x": 160, "mission_clear": False},
        {"max_checkpoint": 2, "died": False, "mission_clear": False},
    ]
    agg = aggregate_attempts(curr)
    assert agg["episodes"] == 4
    assert agg["frontier_cp"] == 3
    assert agg["reach_cp"]["0"] == 1.0
    assert agg["reach_cp"]["2"] == 0.75
    assert agg["death_wall"]["death_room"] == "0x06"
    assert agg["death_wall"]["count"] == 2

    prev_agg = aggregate_attempts(prev)
    delta = delta_aggregates(agg, prev_agg)
    assert delta["available"] is True
    assert delta["frontier_cp"]["delta"] == 1
    assert delta["reach_cp"]["2"]["curr"] == 0.75
    assert delta["reach_cp"]["2"]["prev"] == 0.5

    board = build_broadcast_board(
        model_version="gen1",
        curr_records=curr,
        prev_records=prev,
        mode="editorial",
    )
    assert board["schema"] == "broadcast_board/v1"
    assert board["model_version"] == "gen1"
    assert board["prev_model_version"] == "gen0"
    assert board["mode"] == "editorial"
    assert board["support_line"] == "Поддержать проект"
    assert "ETA" not in str(board).upper()
    assert "GPU" not in str(board).upper()
    assert "донат" not in str(board).lower()
