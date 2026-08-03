"""Session snapshot / rollback для genN.prev.*."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from train.checkpointing import (
    prev_checkpoint_path,
    prev_sidecar_path,
    read_sidecar,
    rollback_prev_session,
    sidecar_path,
    snapshot_prev_session,
)


def _touch_zip(path: Path, content: bytes = b"gen-v1") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _write_sidecar(checkpoint: Path, *, num_timesteps: int = 100) -> None:
    sidecar_path(checkpoint).write_text(
        json.dumps(
            {
                "target_timesteps": 500_000,
                "game": "g",
                "mission": "m",
                "n_envs": 6,
                "save_state": "save_states/cp.fc0",
                "num_timesteps": num_timesteps,
            }
        ),
        encoding="utf-8",
    )


def test_snapshot_and_rollback_roundtrip(tmp_path: Path) -> None:
    out = tmp_path / "models" / "gen0.zip"
    _touch_zip(out, b"gen-v1")
    _write_sidecar(out, num_timesteps=100)

    snapshot_prev_session(out)
    assert prev_checkpoint_path(out).read_bytes() == b"gen-v1"
    assert read_sidecar(out)["num_timesteps"] == 100

    _touch_zip(out, b"gen-v2")
    _write_sidecar(out, num_timesteps=200)

    rollback_prev_session(out)
    assert out.read_bytes() == b"gen-v1"
    assert read_sidecar(out)["num_timesteps"] == 100


def test_rollback_without_prev_exits(tmp_path: Path) -> None:
    out = tmp_path / "models" / "gen0.zip"
    with pytest.raises(SystemExit, match="no previous session snapshot"):
        rollback_prev_session(out)


def test_snapshot_leaves_original_until_train_mutates(tmp_path: Path) -> None:
    out = tmp_path / "models" / "gen0.zip"
    _touch_zip(out, b"before")
    snapshot_prev_session(out)
    assert out.read_bytes() == b"before"
    assert not prev_sidecar_path(out).is_file()
