"""Unit: BC head resolution из playthrough_manifest + policy_heads."""
from __future__ import annotations

import pytest

from train.bc_pretrain import checkpoint_id_from_save_rel, checkpoint_id_to_head_map, resolve_bc_head_id
from train.phase_heads import load_policy_heads_spec

_SAMPLE_HEAD_SAVE_STATES = {
    "title": [{"id": "cp_title0", "frame": 20, "label": "title_screen"}],
    "gameplay": [
        {"id": "cp_gameplay0", "frame": 1243, "label": "level_start"},
        {"id": "cp_gameplay1", "frame": 1506, "label": "after_second_ladder"},
    ],
}


def test_checkpoint_id_from_save_rel() -> None:
    assert checkpoint_id_from_save_rel("save_states/cp_gameplay0.fc0") == "cp_gameplay0"


def test_resolve_bc_head_from_segment_save_state() -> None:
    heads = load_policy_heads_spec("rushn_attack")
    assert heads is not None
    seg = {
        "id": "seg_002",
        "frame_start": 1243,
        "save_state": "save_states/cp_gameplay0.fc0",
    }
    assert (
        resolve_bc_head_id(
            seg, head_save_states=_SAMPLE_HEAD_SAVE_STATES, heads_spec=heads
        )
        == "gameplay"
    )


def test_resolve_bc_head_title_segment() -> None:
    heads = load_policy_heads_spec("rushn_attack")
    assert heads is not None
    seg = {
        "id": "seg_001",
        "frame_start": 1,
        "save_state": "save_states/cp_title0.fc0",
    }
    assert (
        resolve_bc_head_id(seg, head_save_states=_SAMPLE_HEAD_SAVE_STATES, heads_spec=heads)
        == "title"
    )


def test_resolve_bc_head_explicit_bc_head() -> None:
    heads = load_policy_heads_spec("rushn_attack")
    assert heads is not None
    seg = {"id": "x", "bc_head": "bossfight"}
    assert resolve_bc_head_id(seg, head_save_states=None, heads_spec=heads) == "bossfight"


def test_resolve_bc_head_unknown_bc_head_raises() -> None:
    heads = load_policy_heads_spec("rushn_attack")
    assert heads is not None
    with pytest.raises(ValueError, match="bc_head"):
        resolve_bc_head_id({"id": "x", "bc_head": "nope"}, head_save_states=None, heads_spec=heads)


def test_checkpoint_id_to_head_map_nonempty() -> None:
    m = checkpoint_id_to_head_map(_SAMPLE_HEAD_SAVE_STATES)
    assert m.get("cp_gameplay0") == "gameplay"
    assert m.get("cp_title0") == "title"
