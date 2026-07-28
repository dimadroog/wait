"""Режимы run_inference: pool vs live."""
from __future__ import annotations

import argparse

import pytest

from stream.run_inference import validate_inference_args


def _ns(**kwargs: object) -> argparse.Namespace:
    base = {
        "live": False,
        "playlist_no_dedupe": False,
        "wipe_gen_logs": False,
        "playlist_cnt": None,
    }
    base.update(kwargs)
    return argparse.Namespace(**base)


def test_validate_pool_ok() -> None:
    validate_inference_args(_ns())
    validate_inference_args(_ns(playlist_cnt=13))


def test_validate_live_ok() -> None:
    validate_inference_args(_ns(live=True), argv=["--live", "--stochastic"])


@pytest.mark.parametrize(
    "flag",
    ["playlist_no_dedupe", "wipe_gen_logs"],
)
def test_validate_live_rejects_pool_flags(flag: str) -> None:
    with pytest.raises(SystemExit, match="--live"):
        validate_inference_args(_ns(live=True, **{flag: True}), argv=["--live"])


def test_validate_live_rejects_playlist_cnt_in_argv() -> None:
    with pytest.raises(SystemExit, match="--playlist-cnt"):
        validate_inference_args(
            _ns(live=True, playlist_cnt=5),
            argv=["--live", "--playlist-cnt", "5"],
        )


def test_validate_live_allows_default_playlist_cnt_attr() -> None:
    """Default None на args не конфликт, если флага нет в argv."""
    validate_inference_args(_ns(live=True, playlist_cnt=None), argv=["--live"])
