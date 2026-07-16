"""FCEUX: FM2 movie readonly regression (ISSUE_INFERENCE — сломанный путь).

Целевой replay — tests/test_inference_replay_fceux.py (jsonl emulation).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fm2_export import build_empty_fm2, default_fm2_template, episode_fm2_guid  # noqa: E402
from fm2_playback import probe_movie_playback, probe_movie_playback_ppu  # noqa: E402
from project_paths import artifact_quarantine_dir, cleanup_artifact_quarantine, resolve_rom  # noqa: E402
from ram_map_load import load_ram_addresses  # noqa: E402

_MISSION = Path(__file__).resolve().parents[1] / "games" / "rushn_attack" / "missions" / "m1"
_INFERENCE_CP0 = _MISSION / "states" / "inference_cp0.fc0"
_CLEAR_FM2 = _MISSION / "reference" / "clear.fm2"


def _ram_addrs(mission: Path) -> dict[str, int]:
    addrs = load_ram_addresses(mission)
    out: dict[str, int] = {}
    for key in ("room", "x", "lives"):
        raw = addrs[key]
        out[key] = int(str(raw), 16) if str(raw).startswith("0x") else int(raw)
    return out


def _assert_gameplay_ram(probe: dict, *, mf: int) -> None:
    """Критерий RAM @ bootstrap mf (inference_cp0 embed)."""
    assert probe.get("ok") is True, probe
    assert probe.get("movie_active") is True, probe
    assert probe.get("mf", 0) >= mf, probe
    assert probe.get("room") == 0, probe
    assert probe.get("x") == 129, (
        f"ISSUE_INFERENCE open: expected gameplay x=129 at mf>={mf}, got {probe!r}"
    )


def _assert_ppu_heuristic(probe: dict, *, title_like: bool) -> None:
    ppu = probe.get("ppu_heuristic") or {}
    assert ppu.get("ok") is True, ppu
    assert probe.get("screenshot_ok") is True, probe
    assert ppu.get("title_like") is title_like, (
        f"PPU heuristic mismatch: expected title_like={title_like}, got {ppu!r} (probe={probe!r})"
    )


@pytest.fixture
def playback_probe_dir() -> Path:
    path = artifact_quarantine_dir("bench", "fm2_playback_probe")
    path.mkdir(parents=True, exist_ok=True)
    yield path
    cleanup_artifact_quarantine("bench", "fm2_playback_probe")


@pytest.mark.requires_fceux
def test_clear_fm2_playback_ram_probe_mf18(mission_m1: Path, playback_probe_dir: Path) -> None:
    """Эталон power-on: на mf=18 ожидаем gameplay RAM (x=129)."""
    if not _CLEAR_FM2.is_file():
        pytest.skip(f"missing {_CLEAR_FM2}")
    probe = probe_movie_playback(
        _CLEAR_FM2,
        resolve_rom("rushn_attack"),
        playback_probe_dir / "clear_staging",
        playback_probe_dir / "clear_probe",
        ram=_ram_addrs(mission_m1),
        probe_at_mf=18,
        timeout_sec=120.0,
    )
    _assert_gameplay_ram(probe, mf=18)


@pytest.mark.requires_fceux
def test_inference_embed_fm2_playback_ram_probe_mf8(mission_m1: Path, playback_probe_dir: Path) -> None:
    """Inference-клип с embed inference_cp0: probe @ mf=8."""
    if not _INFERENCE_CP0.is_file():
        pytest.skip(f"missing {_INFERENCE_CP0}")
    fm2 = playback_probe_dir / "inference_probe.fm2"
    build_empty_fm2(
        fm2,
        template=default_fm2_template("rushn_attack", "m1"),
        save_state_path=_INFERENCE_CP0,
        guid=episode_fm2_guid(salt="n4-test"),
        num_frames=60,
    )
    probe = probe_movie_playback(
        fm2,
        resolve_rom("rushn_attack"),
        playback_probe_dir / "inf_staging",
        playback_probe_dir / "inf_probe",
        ram=_ram_addrs(mission_m1),
        probe_at_mf=8,
        timeout_sec=90.0,
    )
    _assert_gameplay_ram(probe, mf=8)


@pytest.mark.requires_fceux
@pytest.mark.movie_regression
def test_movie_embed_fm2_ppu_title_at_mf8_regression(
    mission_m1: Path, playback_probe_dir: Path
) -> None:
    """Регрессия: movie readonly + embed — PPU title @ mf=8 (не целевой путь 3.4)."""
    if not _INFERENCE_CP0.is_file():
        pytest.skip(f"missing {_INFERENCE_CP0}")
    fm2 = playback_probe_dir / "inference_ppu_probe.fm2"
    build_empty_fm2(
        fm2,
        template=default_fm2_template("rushn_attack", "m1"),
        save_state_path=_INFERENCE_CP0,
        guid=episode_fm2_guid(salt="n4-ppu-test"),
        num_frames=60,
    )
    probe = probe_movie_playback_ppu(
        fm2,
        resolve_rom("rushn_attack"),
        playback_probe_dir / "inf_ppu_staging",
        playback_probe_dir / "inf_ppu_probe",
        ram=_ram_addrs(mission_m1),
        probe_at_mf=8,
        timeout_sec=90.0,
    )
    _assert_gameplay_ram(probe, mf=8)
    _assert_ppu_heuristic(probe, title_like=True)
