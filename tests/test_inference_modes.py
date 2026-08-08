"""Валидация CLI: pool vs live."""
from __future__ import annotations

from argparse import Namespace

import pytest

from stream.run_inference import validate_inference_args


def _ns(**kwargs):
    base = {
        "live": False,
        "wipe_gen_logs": False,
        "episodes": None,
    }
    base.update(kwargs)
    return Namespace(**base)


def test_validate_pool_ok() -> None:
    validate_inference_args(_ns(episodes=13))


def test_validate_live_ok() -> None:
    validate_inference_args(_ns(live=True), argv=["--live"])


@pytest.mark.parametrize("flag", ["wipe_gen_logs"])
def test_validate_live_rejects_pool_only_flags(flag: str) -> None:
    with pytest.raises(SystemExit, match=flag.replace("_", "-")):
        validate_inference_args(_ns(live=True, **{flag: True}), argv=["--live"])


def test_validate_live_rejects_episodes_in_argv() -> None:
    with pytest.raises(SystemExit, match="--episodes"):
        validate_inference_args(
            _ns(live=True, episodes=5),
            argv=["--live", "--episodes", "5"],
        )


def test_validate_live_allows_default_episodes_attr() -> None:
    """Атрибут episodes=None без --episodes в argv — ок для live."""
    validate_inference_args(_ns(live=True, episodes=None), argv=["--live"])
