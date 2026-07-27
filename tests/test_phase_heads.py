"""Unit: phase→head mapping, action masks, isolation from YAML (G6)."""
from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from train.phase_heads import (
    build_action_mask_table,
    evaluate_phase_head_gate,
    parse_policy_heads_spec,
)


def _spec(**overrides):
    raw = {
        "default_head": "gameplay",
        "heads": ["intro", "gameplay"],
        "phase_to_head": {"title": "intro", "intro": "intro", "gameplay": "gameplay"},
        "action_masks": {"intro": ["", "start"]},
        "isolation": {
            "forbid": [{"head": "gameplay", "phases": ["title", "intro"]}],
            "required_phases": ["gameplay"],
        },
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


def test_isolation_forbid_from_yaml() -> None:
    spec = _spec()
    assert spec.is_forbidden_pair("gameplay", "title")
    assert spec.is_forbidden_pair("gameplay", "intro")
    assert not spec.is_forbidden_pair("gameplay", "gameplay")
    assert not spec.is_forbidden_pair("intro", "title")
    assert spec.required_phases == ("gameplay",)


def test_isolation_absent_means_no_forbid() -> None:
    raw = {
        "default_head": "gameplay",
        "heads": ["intro", "gameplay"],
        "phase_to_head": {"title": "intro", "gameplay": "gameplay"},
    }
    spec = parse_policy_heads_spec(raw)
    assert spec.isolation_forbid == ()
    assert spec.required_phases == ()
    assert not spec.is_forbidden_pair("gameplay", "title")


def test_isolation_forbid_validates_head() -> None:
    with pytest.raises(ValueError, match="not in heads"):
        _spec(
            isolation={
                "forbid": [{"head": "missing", "phases": ["title"]}],
                "required_phases": [],
            }
        )


def test_evaluate_gate_reads_yaml_rules() -> None:
    """G6: gate из синтетического YAML, без литералов title/intro в вызове."""
    spec = parse_policy_heads_spec(
        {
            "default_head": "combat",
            "heads": ["menu", "combat"],
            "phase_to_head": {"menu": "menu", "combat": "combat"},
            "isolation": {
                "forbid": [{"head": "combat", "phases": ["menu"]}],
                "required_phases": ["combat"],
            },
        }
    )
    ok, errors = evaluate_phase_head_gate(
        forbidden_steps=0,
        total_steps=10,
        phase_step_counts={"menu": 2, "combat": 8},
        spec=spec,
    )
    assert ok and not errors

    ok, errors = evaluate_phase_head_gate(
        forbidden_steps=3,
        total_steps=10,
        phase_step_counts={"menu": 3, "combat": 7},
        spec=spec,
    )
    assert not ok
    assert any("isolation" in e for e in errors)

    ok, errors = evaluate_phase_head_gate(
        forbidden_steps=0,
        total_steps=10,
        phase_step_counts={"menu": 10},
        spec=spec,
    )
    assert not ok
    assert any("combat" in e for e in errors)


def test_no_hardcoded_title_intro_tuple_in_train_sources() -> None:
    """Регрессия G6: в src/train нет единственного правила (\"title\",\"intro\")."""
    root = Path(__file__).resolve().parents[1] / "src" / "train"
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if '("title", "intro")' in text or "('title', 'intro')" in text:
            offenders.append(path.name)
        if "gameplay_on_title_intro" in text:
            offenders.append(path.name)
    assert offenders == []
