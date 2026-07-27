"""Режимы model-in / model-out — только tmp_path (не mission gen0.zip)."""
from __future__ import annotations

from pathlib import Path

import pytest

from train.checkpointing import note_n_envs_change, resolve_train_model_mode


def _touch_zip(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"PK\x05\x06" + b"\x00" * 18)  # minimal zip-like stub
    return path


def test_scratch_when_out_missing(tmp_path: Path) -> None:
    out = tmp_path / "models" / "gen0.zip"
    assert resolve_train_model_mode(out, None, overwrite=False) == "scratch"


def test_continue_when_out_exists(tmp_path: Path) -> None:
    out = _touch_zip(tmp_path / "gen0.zip")
    assert resolve_train_model_mode(out, None, overwrite=False) == "continue"


def test_scratch_replace_with_overwrite(tmp_path: Path) -> None:
    out = _touch_zip(tmp_path / "gen0.zip")
    assert resolve_train_model_mode(out, None, overwrite=True) == "scratch"


def test_from_ancestor_when_out_missing(tmp_path: Path) -> None:
    ancestor = _touch_zip(tmp_path / "gen0.zip")
    out = tmp_path / "gen1.zip"
    assert resolve_train_model_mode(out, ancestor, overwrite=False) == "from_ancestor"


def test_from_ancestor_refuse_when_out_exists(tmp_path: Path) -> None:
    ancestor = _touch_zip(tmp_path / "gen0.zip")
    out = _touch_zip(tmp_path / "gen1.zip")
    with pytest.raises(SystemExit, match="already exists"):
        resolve_train_model_mode(out, ancestor, overwrite=False)


def test_from_ancestor_replace_with_overwrite(tmp_path: Path) -> None:
    ancestor = _touch_zip(tmp_path / "gen0.zip")
    out = _touch_zip(tmp_path / "gen1.zip")
    assert resolve_train_model_mode(out, ancestor, overwrite=True) == "from_ancestor"


def test_same_in_out_refused(tmp_path: Path) -> None:
    z = _touch_zip(tmp_path / "gen0.zip")
    with pytest.raises(SystemExit, match="same file"):
        resolve_train_model_mode(z, z, overwrite=False)
    with pytest.raises(SystemExit, match="same file"):
        resolve_train_model_mode(z, z, overwrite=True)


def test_model_in_missing_refused(tmp_path: Path) -> None:
    out = tmp_path / "gen1.zip"
    missing = tmp_path / "nope.zip"
    with pytest.raises(SystemExit, match="model-in not found"):
        resolve_train_model_mode(out, missing, overwrite=False)


def test_note_n_envs_change_continue_prefix() -> None:
    msg = note_n_envs_change({"n_envs": 6}, 2)
    assert msg is not None
    assert msg.startswith("continue:")
    assert note_n_envs_change({"n_envs": 2}, 2) is None
