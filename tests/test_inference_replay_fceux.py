"""FCEUX: jsonl emulation replay probes (BACKLOG 3.4 / ISSUE_INFERENCE N4)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from inference_replay import (  # noqa: E402
    DEFAULT_FRAME_SKIP,
    PROBE_EPISODE_GAMEPLAY_FRAME,
    PROBE_RESET_FRAME,
    probe_inference_replay_ppu,
)
from project_paths import artifact_quarantine_dir, cleanup_artifact_quarantine  # noqa: E402
from ram_map_load import load_ram_addresses  # noqa: E402

_MISSION = Path(__file__).resolve().parents[1] / "games" / "rushn_attack" / "missions" / "m1"
_LOGS = _MISSION / "logs"


def _latest_inference_inputs() -> Path | None:
    candidates = sorted(_LOGS.glob("*_inference_inputs.jsonl"), reverse=True)
    return candidates[0] if candidates else None


def _ram_addrs(mission: Path) -> dict[str, int]:
    addrs = load_ram_addresses(mission)
    out: dict[str, int] = {}
    for key in ("room", "x", "lives"):
        raw = addrs[key]
        out[key] = int(str(raw), 16) if str(raw).startswith("0x") else int(raw)
    return out


def _assert_gameplay_ram(probe: dict, *, frame: int) -> None:
    assert probe.get("ok") is True, probe
    assert probe.get("playback_frame", 0) >= frame, probe
    assert probe.get("room") == 0, probe
    assert probe.get("x") == 129, (
        f"expected gameplay x=129 at frame>={frame}, got {probe!r}"
    )


def _assert_ppu_gameplay(probe: dict) -> None:
    ppu = probe.get("ppu_heuristic") or {}
    assert ppu.get("ok") is True, ppu
    assert probe.get("screenshot_ok") is True, probe
    assert ppu.get("title_like") is False, ppu
    assert ppu.get("gameplay_like_ppu_heuristic") is True, ppu


@pytest.fixture
def replay_probe_dir() -> Path:
    path = artifact_quarantine_dir("bench", "inference_replay_probe")
    path.mkdir(parents=True, exist_ok=True)
    yield path
    cleanup_artifact_quarantine("bench", "inference_replay_probe")


@pytest.fixture
def minimal_jsonl_inputs(replay_probe_dir: Path) -> Path:
    """3 env steps × frame_skip."""
    p = replay_probe_dir / "minimal_inputs.jsonl"
    lines = []
    for step in range(3):
        lines.append(
            json.dumps(
                {
                    "episode": 1,
                    "step": step,
                    "frame": 20 + step * 4,
                    "action": "",
                }
            )
        )
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


@pytest.mark.requires_fceux
def test_jsonl_replay_ram_at_frame8(
    mission_m1: Path,
    replay_probe_dir: Path,
    minimal_jsonl_inputs: Path,
) -> None:
    probe = probe_inference_replay_ppu(
        minimal_jsonl_inputs,
        1,
        replay_probe_dir / "staging",
        replay_probe_dir / "probe",
        ram=_ram_addrs(mission_m1),
        probe_at_frame=8,
        frame_skip=DEFAULT_FRAME_SKIP,
        timeout_sec=90.0,
    )
    _assert_gameplay_ram(probe, frame=8)


@pytest.mark.requires_fceux
def test_jsonl_replay_ppu_gameplay_at_reset(
    mission_m1: Path,
    replay_probe_dir: Path,
    minimal_jsonl_inputs: Path,
) -> None:
    """Emulation+jsonl: gameplay PPU сразу после inference_cp0 (в отличие от movie @ mf=8)."""
    probe = probe_inference_replay_ppu(
        minimal_jsonl_inputs,
        1,
        replay_probe_dir / "staging_ppu",
        replay_probe_dir / "probe_ppu",
        ram=_ram_addrs(mission_m1),
        probe_at_frame=PROBE_RESET_FRAME,
        frame_skip=DEFAULT_FRAME_SKIP,
        timeout_sec=90.0,
    )
    _assert_gameplay_ram(probe, frame=PROBE_RESET_FRAME)
    _assert_ppu_gameplay(probe)


@pytest.mark.requires_fceux
@pytest.mark.skipif(_latest_inference_inputs() is None, reason="local inference logs required")
def test_jsonl_replay_ppu_gameplay_during_real_episode(
    mission_m1: Path,
    replay_probe_dir: Path,
) -> None:
    """Реальный ep: gameplay PPU в середине replay (не title-attract @ mf=8)."""
    inputs = _latest_inference_inputs()
    assert inputs is not None
    probe = probe_inference_replay_ppu(
        inputs,
        1,
        replay_probe_dir / "staging_ep",
        replay_probe_dir / "probe_ep",
        ram=_ram_addrs(mission_m1),
        probe_at_frame=PROBE_EPISODE_GAMEPLAY_FRAME,
        frame_skip=DEFAULT_FRAME_SKIP,
        timeout_sec=120.0,
    )
    assert probe.get("ok") is True, probe
    assert probe.get("screenshot_ok") is True, probe
    _assert_ppu_gameplay(probe)
