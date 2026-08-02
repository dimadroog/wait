"""Unit: bc_obs_compare frame indexing."""
from __future__ import annotations

import pytest

from bc_obs_compare import frame_to_npz_index


def test_frame_to_npz_index() -> None:
    assert frame_to_npz_index(1034, frame_start=1034, frame_skip=4) == 0
    assert frame_to_npz_index(1038, frame_start=1034, frame_skip=4) == 1
    assert frame_to_npz_index(1202, frame_start=1034, frame_skip=4) == 42
    with pytest.raises(ValueError):
        frame_to_npz_index(1035, frame_start=1034, frame_skip=4)
