from unittest.mock import MagicMock, patch

from train.ram_mitigations import (
    DEFAULT_N_ENVS_16GB,
    RolloutGcCallback,
    warn_if_n_envs_high_for_ram,
)


def test_rollout_gc_callback_collects_on_rollout_end() -> None:
    cb = RolloutGcCallback()
    cb.model = MagicMock()
    with patch("train.ram_mitigations.gc.collect") as collect:
        assert cb._on_step() is True
        assert cb._on_rollout_end() is True
    collect.assert_called_once()


def test_warn_if_n_envs_high_for_ram_prints(capsys) -> None:
    warn_if_n_envs_high_for_ram(8)
    out = capsys.readouterr().out
    assert "WARNING [H2]" in out
    assert str(DEFAULT_N_ENVS_16GB) in out


def test_warn_if_n_envs_high_for_ram_silent_at_recommended(capsys) -> None:
    warn_if_n_envs_high_for_ram(DEFAULT_N_ENVS_16GB)
    assert capsys.readouterr().out == ""
