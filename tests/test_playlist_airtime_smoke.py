"""Smoke: --target-airtime 2m → playlist airtime ≥ target → play_inference_fm2 OK.

Не scripts/*_smoke*.py (гигиена артефактов). Inference пишет в games/.../logs/ (явно).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from achievements.airtime import measure_playlist_airtime  # noqa: E402
from project_paths import mission_dir  # noqa: E402

TARGET = "2m"
TARGET_SECONDS = 120.0
# Короткий max-steps: много death/truncated клипов; airtime набирается hold'ом (~3 с/клип).
BATCH_EPISODES = "8"
MAX_STEPS = "80"
MAX_BATCHES = "40"


@pytest.mark.requires_fceux
@pytest.mark.slow
def test_target_airtime_2m_playlist_and_play() -> None:
    mission = mission_dir("rushn_attack", "m1")
    model = mission / "models" / "gen0.zip"
    if not model.is_file():
        pytest.skip(f"missing model: {model}")

    py = sys.executable
    collect = [
        py,
        "-u",
        str(_REPO / "src" / "stream" / "run_inference.py"),
        "--game",
        "rushn_attack",
        "--mission",
        "m1",
        "--model",
        "gen0.zip",
        "--stochastic",
        "--wipe-gen-logs",
        "--target-airtime",
        TARGET,
        "--episodes",
        BATCH_EPISODES,
        "--max-steps",
        MAX_STEPS,
        "--max-airtime-batches",
        MAX_BATCHES,
    ]
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}

    print(" ".join(collect), flush=True)
    result = subprocess.run(collect, cwd=str(_REPO), check=False, env=env)
    assert result.returncode == 0, f"run_inference failed (exit {result.returncode})"

    pool = mission / "logs" / "gen0"
    playlist = pool / "playlist.json"
    assert playlist.is_file(), f"missing playlist: {playlist}"
    manifest = json.loads(playlist.read_text(encoding="utf-8"))
    assert "airtime" in manifest, "playlist.json missing airtime summary"
    air = measure_playlist_airtime(playlist)
    print(
        f"smoke airtime={air.seconds:.1f}s ({air.hours:.4f}h) clips={air.clip_count} "
        f"target={TARGET_SECONDS:.0f}s",
        flush=True,
    )
    assert air.seconds + 1e-6 >= TARGET_SECONDS, (
        f"playlist airtime {air.seconds:.1f}s < target {TARGET_SECONDS:.0f}s"
    )
    assert float(manifest["airtime"]["seconds"]) + 1e-6 >= TARGET_SECONDS

    play = [
        py,
        "-u",
        str(_REPO / "scripts" / "play_inference_fm2.py"),
        str(playlist),
        "--game",
        "rushn_attack",
        "--mission",
        "m1",
        "--turbo",
        "--noicon",
        "--skip-preflight",
    ]
    print(" ".join(play), flush=True)
    play_result = subprocess.run(play, cwd=str(_REPO), check=False, env=env)
    assert play_result.returncode == 0, (
        f"play_inference_fm2 failed (exit {play_result.returncode})"
    )
