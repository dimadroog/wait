"""Unit tests for adaptive STEP IPC timeout and retry (FAIL_REPORT R1.1–R1.2)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from fceux_bridge import (
    DEFAULT_TIMEOUT,
    STEP_TIMEOUT_MAX,
    FceuxBridge,
    FceuxBridgeError,
    count_parallel_bridge_sessions,
    step_ipc_timeout,
)


def _bridge_stub(session_id: str = "train_1", *, seq: int = 0):
    bridge = FceuxBridge.__new__(FceuxBridge)
    bridge.session_id = session_id
    bridge._seq = seq
    bridge._proc = MagicMock()
    bridge._proc.poll.return_value = None
    bridge.ipc_dir = MagicMock()
    return bridge


def test_step_ipc_timeout_single_env() -> None:    assert step_ipc_timeout(rank=0, parallel_sessions=1) == 45.0


def test_step_ipc_timeout_rank_and_peers() -> None:
    timeout = step_ipc_timeout(rank=7, parallel_sessions=8)
    assert timeout == min(45.0 + 7 * 12.0, STEP_TIMEOUT_MAX)
    assert timeout > DEFAULT_TIMEOUT


def test_step_ipc_timeout_capped() -> None:
    timeout = step_ipc_timeout(rank=99, parallel_sessions=99)
    assert timeout == STEP_TIMEOUT_MAX


def test_count_parallel_bridge_sessions_empty(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("fceux_bridge.repo_root", lambda: tmp_path)
    assert count_parallel_bridge_sessions() == 0


def test_step_retries_once_on_ipc_timeout(capsys) -> None:
    bridge = _bridge_stub("train_2", seq=1)
    with patch.object(bridge, "request") as mock_request:
        mock_request.side_effect = [
            FceuxBridgeError("IPC timeout for STEP (45.0s) seq=1"),
            {"ok": True, "seq": 2},
        ]
        with patch.object(bridge, "_step_timeout", return_value=45.0):
            result = FceuxBridge.step(bridge, "right")
    assert result["ok"] is True
    assert mock_request.call_count == 2
    out = capsys.readouterr().out
    assert "STEP retry 1/2 rank=2 seq=1" in out


def test_step_does_not_retry_non_timeout_error() -> None:
    bridge = _bridge_stub()
    with patch.object(bridge, "request") as mock_request:
        mock_request.side_effect = FceuxBridgeError("STEP failed")
        with patch.object(bridge, "_step_timeout", return_value=45.0):
            with pytest.raises(FceuxBridgeError, match="STEP failed"):
                FceuxBridge.step(bridge, "right")
    assert mock_request.call_count == 1


def test_step_raises_after_retry_exhausted() -> None:
    bridge = _bridge_stub("bench_3")
    with patch.object(bridge, "request") as mock_request:
        mock_request.side_effect = FceuxBridgeError("IPC timeout for STEP (72.0s) seq=1")
        with patch.object(bridge, "_step_timeout", return_value=72.0):
            with pytest.raises(FceuxBridgeError, match="IPC timeout for STEP"):
                FceuxBridge.step(bridge, "right")
    assert mock_request.call_count == 3