"""Unit tests for bridge preflight (FAIL_REPORT R0.1)."""
from __future__ import annotations

from unittest.mock import patch

from train.env_factory import (
    count_orphan_fceux_bridge,
    count_orphan_train_python,
    kill_orphan_fceux_bridge,
    preflight_bridge_sessions,
    require_clean_preflight,
)


def test_count_orphan_non_windows_returns_zero() -> None:
    with patch("train.env_factory.sys.platform", "linux"):
        assert count_orphan_fceux_bridge() == 0


def test_preflight_warns_when_orphans_present(capsys) -> None:
    with patch("train.env_factory.count_orphan_fceux_bridge", side_effect=[2, 0]):
        with patch("train.env_factory.count_orphan_train_python", side_effect=[1, 0]):
            with patch("train.env_factory.cleanup_bridge_sessions") as cleanup:
                before = preflight_bridge_sessions(label="test")
    assert before == 3
    assert cleanup.call_count == 2
    out = capsys.readouterr().out
    assert "WARNING [test]: 2 orphan fceux64.exe" in out
    assert "WARNING [test]: 1 orphan python" in out
    assert "orphans cleared" in out


def test_preflight_ok_when_clean(capsys) -> None:
    with patch("train.env_factory.count_orphan_fceux_bridge", return_value=0):
        with patch("train.env_factory.count_orphan_train_python", return_value=0):
            with patch("train.env_factory.cleanup_bridge_sessions"):
                preflight_bridge_sessions(label="test")
    out = capsys.readouterr().out
    assert "no orphan processes" in out
    assert "WARNING" not in out


def test_require_clean_preflight_aborts_when_orphans_remain() -> None:
    with patch("train.env_factory.count_orphan_fceux_bridge", side_effect=[0, 1]):
        with patch("train.env_factory.count_orphan_train_python", return_value=0):
            with patch("train.env_factory.cleanup_bridge_sessions"):
                try:
                    require_clean_preflight(label="test")
                except SystemExit as exc:
                    assert exc.code != 0
                else:
                    raise AssertionError("expected SystemExit")


def test_kill_orphan_skips_non_windows() -> None:
    with patch("train.env_factory.sys.platform", "linux"):
        with patch("train.env_factory._win32_run_ps") as run_ps:
            kill_orphan_fceux_bridge()
    run_ps.assert_not_called()


def test_kill_orphan_runs_fceux_and_python_cleanup() -> None:
    with patch("train.env_factory.sys.platform", "win32"):
        with patch("train.env_factory.os.getpid", return_value=4242):
            with patch("train.env_factory._win32_run_ps") as run_ps:
                kill_orphan_fceux_bridge()
    assert run_ps.call_count == 2
    fceux_script, python_script = run_ps.call_args_list[0].args[0], run_ps.call_args_list[1].args[0]
    assert "fceux64.exe" in fceux_script
    assert "bridge.lua" in fceux_script
    assert "tmp" in fceux_script and "bridge" in fceux_script
    assert "$me = 4242" in python_script
    assert "benchmark_train.py" in python_script
    assert "train_ppo.py" in python_script
