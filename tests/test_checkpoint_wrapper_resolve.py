"""Сборка runtime CP из routes.yaml + route_triggers.yaml."""
from __future__ import annotations

from pathlib import Path

import yaml

from rewards.checkpoint_wrapper import load_resolved_checkpoints


def test_load_resolved_checkpoints_anchor_merge(tmp_path: Path) -> None:
    mission = tmp_path
    (mission / "config").mkdir()
    routes = mission / "config" / "routes.yaml"
    routes.write_text(
        yaml.dump(
            {
                "checkpoints": [
                    {
                        "id": 1,
                        "name": "node",
                        "anchor": "cp_gameplay1",
                        "requires_checkpoint": 0,
                    },
                    {"id": 2, "name": "clear", "trigger": {"flag": "mission_complete"}},
                ]
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    triggers = mission / "config" / "route_triggers.yaml"
    triggers.write_text(
        yaml.dump(
            {"triggers": {"cp_gameplay1": {"room": "0x00", "min_stage": 3}}},
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    cps = load_resolved_checkpoints(routes, triggers)
    assert cps[0]["trigger"] == {"room": "0x00", "min_stage": 3, "requires_checkpoint": 0}
    assert cps[1]["trigger"] == {"flag": "mission_complete"}


def test_load_resolved_checkpoints_legacy_inline(tmp_path: Path) -> None:
    mission = tmp_path
    (mission / "config").mkdir()
    routes = mission / "config" / "routes.yaml"
    routes.write_text(
        yaml.dump(
            {
                "checkpoints": [
                    {"id": 1, "name": "legacy", "trigger": {"room": "0x00", "min_stage": 1}},
                ]
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    cps = load_resolved_checkpoints(routes, mission / "config" / "route_triggers.yaml")
    assert cps[0]["trigger"] == {"room": "0x00", "min_stage": 1}


def test_load_resolved_missing_binding_raises(tmp_path: Path) -> None:
    mission = tmp_path
    (mission / "config").mkdir()
    routes = mission / "config" / "routes.yaml"
    routes.write_text(
        yaml.dump({"checkpoints": [{"id": 1, "anchor": "cp_gameplay1"}]}, allow_unicode=True),
        encoding="utf-8",
    )
    try:
        load_resolved_checkpoints(routes, mission / "config" / "route_triggers.yaml")
    except ValueError as e:
        assert "compile_route_triggers" in str(e)
    else:
        raise AssertionError("expected ValueError")
