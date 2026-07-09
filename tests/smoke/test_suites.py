"""Integration smoke — покрытие как scripts/run_smoke.py (BACKLOG 4.1 / 4.3)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"

# Синхронизировать с scripts/run_smoke.py::_suite_commands
SUITE_COMMANDS: dict[str, list[str]] = {
    "bridge": [str(_SCRIPTS / "smoke_bridge.py")],
    "env": [str(_SCRIPTS / "smoke_env.py"), "--steps", "20"],
    "parallel": [
        str(_SCRIPTS / "test_parallel_env.py"),
        "--n-envs",
        "8",
        "--cycles",
        "10",
        "--reset-every",
        "5",
    ],
}


@pytest.mark.requires_fceux
@pytest.mark.parametrize("suite", list(SUITE_COMMANDS))
def test_smoke_suite(suite: str, repo_root: Path) -> None:
    cmd = [sys.executable, *SUITE_COMMANDS[suite]]
    result = subprocess.run(
        cmd,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"smoke:{suite} failed (exit {result.returncode})\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
