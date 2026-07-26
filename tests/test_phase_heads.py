"""Unit: phase→head mapping and action masks (TASK_POLICY_SEPARATION Multi-head)."""
from __future__ import annotations

import warnings

import pytest

from train.phase_heads import build_action_mask_table, parse_policy_heads_spec


def _spec(**overrides):
    raw = {
        "default_head": "gameplay",
        "heads": ["intro", "gameplay"],
        "phase_to_head": {"title": "intro", "intro": "intro", "gameplay": "gameplay"},
        "action_masks": {"intro": ["", "start"]},
    }
    raw.update(overrides)
    return parse_policy_heads_spec(raw)


def test_phase_to_head_mapping() -> None:
    spec = _spec()
    assert spec.head_id_for_phase("title") == "intro"
    assert spec.head_id_for_phase("intro") == "intro"
    assert spec.head_id_for_phase("gameplay") == "gameplay"
    assert spec.head_id_for_phase(None) == "gameplay"
    assert spec.head_id_for_phase("") == "gameplay"


def test_unknown_phase_falls_back_with_warning() -> None:
    spec = _spec()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert spec.head_id_for_phase("boss") == "gameplay"
    assert any("unknown phase_id" in str(w.message) for w in caught)


def test_intro_action_mask_indices() -> None:
    spec = _spec()
    actions = ("", "left", "right", "start")
    intro = spec.allowed_action_indices("intro", actions)
    assert intro == [0, 3]
    assert spec.allowed_action_indices("gameplay", actions) is None


def test_mask_table_gameplay_allows_all() -> None:
    spec = _spec()
    actions = ("", "left", "right", "A", "B", "start")
    table = build_action_mask_table(spec, actions)
    assert table["intro"].tolist() == [True, False, False, False, False, True]
    assert bool(table["gameplay"].all())


def test_parse_requires_two_heads() -> None:
    with pytest.raises(ValueError, match="≥2"):
        parse_policy_heads_spec(
            {"default_head": "a", "heads": ["a"], "phase_to_head": {}}
        )
