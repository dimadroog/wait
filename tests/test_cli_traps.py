"""CLI traps: model stem, task vs CLI, wipe states/demos, timesteps reduce."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from jsonl_logs import require_consistent_model_version, resolve_default_model_version
from project_paths import clear_save_state_files
from train.checkpointing import resolve_target_timesteps
from train.train_ppo import apply_task_defaults, cli_explicit_fields


def test_model_stem_conflict_exits() -> None:
    with pytest.raises(SystemExit, match="stem"):
        require_consistent_model_version(model="gen0.zip", model_version="gen1")


def test_model_stem_matching_ok(tmp_path: Path) -> None:
    require_consistent_model_version(model="gen0.zip", model_version="gen0")
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "latest.zip").write_bytes(b"x")
    assert resolve_default_model_version(tmp_path, model="gen1.zip", model_version="gen1") == "gen1"


def test_cli_explicit_fields_detects_flags() -> None:
    assert "timesteps" in cli_explicit_fields(["--timesteps", "1000"])
    assert "model_in" in cli_explicit_fields(["--model-in=models/gen0.zip"])
    assert "timesteps" not in cli_explicit_fields(["--n-envs", "4"])


def test_apply_task_defaults_cli_wins(tmp_path: Path) -> None:
    mission = tmp_path
    args = SimpleNamespace(
        model_in=None,
        model_out=None,
        save_state=None,
        reward_profile="default",
        timesteps=500_000,
        learning_rate=2.5e-4,
        bc_epochs=0,
        bc_demo=None,
    )
    task = {
        "ppo_timesteps": 12_000,
        "model_out": "models/from_task.zip",
        "reward_profile": "hot_zone",
    }
    apply_task_defaults(args, task, mission, cli_explicit=frozenset({"timesteps"}))
    assert args.timesteps == 500_000  # CLI explicit → task ignored
    assert args.model_out == str(mission / "models" / "from_task.zip")
    assert args.reward_profile == "hot_zone"

    apply_task_defaults(
        args,
        task,
        mission,
        cli_explicit=frozenset(),
    )
    assert args.timesteps == 12_000


def test_resolve_target_exits_when_explicit_cli_lower() -> None:
    with pytest.raises(SystemExit, match="allow-reduce-target"):
        resolve_target_timesteps(
            10_000,
            {"target_timesteps": 20_000},
            cli_timesteps_explicit=True,
            allow_reduce=False,
        )


def test_resolve_target_allow_reduce() -> None:
    assert (
        resolve_target_timesteps(
            10_000,
            {"target_timesteps": 20_000},
            cli_timesteps_explicit=True,
            allow_reduce=True,
        )
        == 10_000
    )


def test_resolve_target_keeps_sidecar_when_cli_default() -> None:
    assert (
        resolve_target_timesteps(
            10_000,
            {"target_timesteps": 20_000},
            cli_timesteps_explicit=False,
        )
        == 20_000
    )


def test_resolve_target_raises_when_cli_higher() -> None:
    assert resolve_target_timesteps(100_000, {"target_timesteps": 20_000}) == 100_000


def test_clear_save_states_keeps_extras(tmp_path: Path) -> None:
    states = tmp_path / "save_states"
    states.mkdir()
    (states / "cp_gameplay0.fc0").write_bytes(b"a")
    (states / "extra.fc0").write_bytes(b"b")
    plan = [{"file": "cp_gameplay0.fc0", "slot": 0}]
    removed = clear_save_state_files(states, plan, replace_all=False)
    assert [p.name for p in removed] == ["cp_gameplay0.fc0"]
    assert not (states / "cp_gameplay0.fc0").exists()
    assert (states / "extra.fc0").is_file()


def test_clear_save_states_replace_all(tmp_path: Path) -> None:
    states = tmp_path / "save_states"
    states.mkdir()
    (states / "cp_gameplay0.fc0").write_bytes(b"a")
    (states / "extra.fc0").write_bytes(b"b")
    removed = clear_save_state_files(
        states, [{"file": "cp_gameplay0.fc0"}], replace_all=True
    )
    assert {p.name for p in removed} == {"cp_gameplay0.fc0", "extra.fc0"}
    assert list(states.glob("*.fc0")) == []
