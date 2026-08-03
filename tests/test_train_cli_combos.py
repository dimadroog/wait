"""validate_cli_combos — взаимоисключающие флаги train_ppo."""
from __future__ import annotations

import argparse

import pytest

from train.train_ppo import validate_cli_combos


def _args(**kwargs: object) -> argparse.Namespace:
    defaults = {
        "rollback": False,
        "scratch": False,
        "model_in": None,
        "smoke": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def test_rollback_forbids_scratch() -> None:
    with pytest.raises(SystemExit, match="--rollback cannot be combined with --scratch"):
        validate_cli_combos(_args(rollback=True, scratch=True), explicit=frozenset())


def test_rollback_forbids_extra_train_flags() -> None:
    with pytest.raises(SystemExit, match="omit train flags"):
        validate_cli_combos(_args(rollback=True), explicit=frozenset({"timesteps"}))


def test_scratch_forbids_model_in() -> None:
    with pytest.raises(SystemExit, match="--scratch cannot be combined with --model-in"):
        validate_cli_combos(_args(scratch=True, model_in="x.zip"), explicit=frozenset())
