"""Номинации hybrid: wall / new_frontier / regression (slug-generic types)."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from achievements.evaluator import evaluate_records, overlay_payload  # noqa: E402

_HYBRID_CONFIG = {
    "nominations": [
        {"slug": "wall", "idx": 3, "type": "death_cluster", "min_count": 3, "tier": "skull", "label": "Wall"},
        {"slug": "new_frontier", "idx": 2, "type": "new_max_checkpoint", "tier": "gold", "label": "Frontier"},
        {"slug": "regression", "idx": 5, "type": "regression", "min_drop": 2, "tier": "silver", "label": "Regression"},
    ]
}


def _ts(h: int) -> str:
    return datetime(2026, 7, 24, h, 0, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def test_hybrid_nominations_wall_frontier_regression() -> None:
    rows = [
        {
            "episode_id": "a",
            "model_version": "gen1",
            "max_checkpoint": 1,
            "timestamp": _ts(8),
            "died": True,
            "death_room": "0x06",
            "death_x": 160,
        },
        {
            "episode_id": "b",
            "model_version": "gen1",
            "max_checkpoint": 2,
            "timestamp": _ts(9),
            "died": True,
            "death_room": "0x06",
            "death_x": 160,
        },
        {
            "episode_id": "c",
            "model_version": "gen1",
            "max_checkpoint": 2,
            "timestamp": _ts(10),
            "died": True,
            "death_room": "0x06",
            "death_x": 160,
        },
        {
            "episode_id": "d",
            "model_version": "gen1",
            "max_checkpoint": 0,
            "timestamp": _ts(11),
            "died": True,
            "death_room": "0x01",
            "death_x": 8,
        },
    ]
    out = {r["episode_id"]: r for r in evaluate_records(rows, _HYBRID_CONFIG)}

    for eid in ("a", "b", "c"):
        assert "wall" in out[eid]["tags"]
    assert "wall" not in out["d"]["tags"]

    assert "new_frontier" not in out["a"]["tags"]
    assert "new_frontier" in out["b"]["tags"]
    assert "new_frontier" not in out["c"]["tags"]

    assert "regression" in out["d"]["tags"]

    payload = overlay_payload(out["b"], config=_HYBRID_CONFIG)
    assert payload["model_version"] == "gen1"
    assert payload["tag"] == "Frontier"
    assert payload["stats"]["max_cp"] == 2
    assert "reward" not in payload["stats"]
    assert payload["death"]["room"] == "0x06"
