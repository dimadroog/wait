"""FCEUX: achievement_overlay.lua (GUI hooks path) visual smoke."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from inference_replay import (  # noqa: E402
    DEFAULT_FRAME_SKIP,
    PROBE_EPISODE_GAMEPLAY_FRAME,
    PROBE_RESET_FRAME,
    probe_playback_overlay_ppu,
    replay_frame_count,
    run_inference_playback,
)
from project_paths import artifact_quarantine_dir, cleanup_artifact_quarantine  # noqa: E402

_MISSION = Path(__file__).resolve().parents[1] / "games" / "rushn_attack" / "missions" / "m1"
_LOGS = _MISSION / "logs"


def _latest_inference_inputs() -> Path | None:
    candidates = sorted(_LOGS.glob("*_inference_inputs.jsonl"), reverse=True)
    return candidates[0] if candidates else None


@pytest.fixture
def overlay_probe_dir() -> Path:
    path = artifact_quarantine_dir("bench", "playback_overlay_probe")
    path.mkdir(parents=True, exist_ok=True)
    yield path
    cleanup_artifact_quarantine("bench", "playback_overlay_probe")


@pytest.fixture
def minimal_jsonl_inputs(overlay_probe_dir: Path) -> Path:
    p = overlay_probe_dir / "minimal_inputs.jsonl"
    lines = [
        json.dumps({"episode": 1, "step": i, "frame": 20 + i * 4, "action": ""})
        for i in range(3)
    ]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


@pytest.mark.requires_fceux
def test_overlay_hook_ppu_at_reset(
    mission_m1: Path,
    overlay_probe_dir: Path,
    minimal_jsonl_inputs: Path,
) -> None:
    """achievement_overlay (register hooks): gameplay PPU @ frame 1."""
    probe = probe_playback_overlay_ppu(
        minimal_jsonl_inputs,
        1,
        overlay_probe_dir / "staging",
        overlay_probe_dir / "tmp",
        overlay_probe_dir / "overlay_f1.png",
        probe_at_frame=PROBE_RESET_FRAME,
        frame_skip=DEFAULT_FRAME_SKIP,
    )
    ppu = probe.get("ppu_heuristic") or {}
    assert probe.get("screenshot_ok") is True, probe
    assert ppu.get("title_like") is False, ppu
    assert ppu.get("gameplay_like_ppu_heuristic") is True, ppu


@pytest.mark.requires_fceux
@pytest.mark.skipif(_latest_inference_inputs() is None, reason="local inference logs required")
def test_overlay_hook_ppu_mid_episode(
    mission_m1: Path,
    overlay_probe_dir: Path,
) -> None:
    inputs = _latest_inference_inputs()
    assert inputs is not None
    probe = probe_playback_overlay_ppu(
        inputs,
        1,
        overlay_probe_dir / "staging_ep",
        overlay_probe_dir / "tmp_ep",
        overlay_probe_dir / "overlay_f200.png",
        probe_at_frame=PROBE_EPISODE_GAMEPLAY_FRAME,
        frame_skip=DEFAULT_FRAME_SKIP,
        timeout_sec=120.0,
    )
    ppu = probe.get("ppu_heuristic") or {}
    assert probe.get("screenshot_ok") is True, probe
    assert ppu.get("title_like") is False, ppu


@pytest.mark.requires_fceux
def test_playback_non_turbo_not_instant(
    mission_m1: Path,
    overlay_probe_dir: Path,
    minimal_jsonl_inputs: Path,
) -> None:
    """Без turbo replay не должен мгновенно проскакивать тысячи кадров."""
    staging = overlay_probe_dir / "staging_play"
    tmp = overlay_probe_dir / "tmp_play"
    frames = replay_frame_count(minimal_jsonl_inputs, 1, frame_skip=DEFAULT_FRAME_SKIP)
    assert frames >= 8
    t0 = time.monotonic()
    run_inference_playback(
        jsonl_path=minimal_jsonl_inputs,
        episode=1,
        staging=staging,
        tmp_dir=tmp,
        turbo=False,
        timeout_sec=90.0,
    )
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.08, f"playback too fast ({elapsed:.3f}s) — turbo leak?"
