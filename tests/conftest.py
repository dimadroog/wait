"""Pytest fixtures and autouse cleanup (BACKLOG 4.3)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from project_paths import (  # noqa: E402
    cleanup_artifact_quarantine,
    cleanup_mission_smoke_checkpoints,
    find_stray_smoke_artifacts,
    mission_dir,
    resolve_fceux_binary,
)
from train.env_factory import cleanup_bridge_sessions  # noqa: E402


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "requires_fceux: integration smoke (FCEUX + mission)")
    config.addinivalue_line("markers", "slow: long IPC stress (minutes)")


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def mission_m1(repo_root: Path) -> Path:
    return mission_dir("rushn_attack", "m1")


@pytest.fixture
def smoke_artifact_dir(tmp_path: Path) -> Path:
    """Per-test writable dir (карантин при необходимости)."""
    return tmp_path


@pytest.fixture(autouse=True)
def _require_fceux_for_marked(request: pytest.FixtureRequest) -> None:
    if request.node.get_closest_marker("requires_fceux") is None:
        return
    try:
        resolve_fceux_binary()
    except FileNotFoundError as e:
        pytest.skip(str(e))


@pytest.fixture(autouse=True)
def _bridge_and_smoke_hygiene(mission_m1: Path) -> None:
    cleanup_bridge_sessions("train_")
    cleanup_bridge_sessions("bench_")
    yield
    cleanup_bridge_sessions("train_")
    cleanup_bridge_sessions("bench_")
    cleanup_artifact_quarantine("smoke")
    cleanup_mission_smoke_checkpoints(mission_m1)
    stray = find_stray_smoke_artifacts(mission_m1)
    assert not stray, f"stray smoke_* in mission checkpoints: {stray}"
