"""FCEUX: FM2 movie readonly regression (ISSUE_INFERENCE — сломанный путь).

Целевой replay — tests/test_inference_replay_fceux.py (jsonl emulation).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fm2_export import build_empty_fm2, default_fm2_template, episode_fm2_guid  # noqa: E402
from fm2_playback import (  # noqa: E402
    probe_movie_playback,
    probe_movie_playback_ppu,
    probe_native_record_replay,
    run_f0_operator_gate,
)
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
    """Критерий RAM @ bootstrap: lives 1..9 (не x=129 — title false positive, G0)."""
    assert probe.get("ok") is True, probe
    assert probe.get("movie_active") is True, probe
    assert probe.get("mf", 0) >= mf, probe
    lives = int(probe.get("lives", -1))
    assert 1 <= lives <= 9, (
        f"expected gameplay lives in 1..9 at mf>={mf}, got {probe!r}"
    )
    assert probe.get("gameplay_like_ram") is True, probe


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
def test_clear_fm2_playback_ram_probe_gameplay_start(
    mission_m1: Path, playback_probe_dir: Path
) -> None:
    """Эталон power-on: на реальном gameplay_start (не mf=18 title) — lives 1..9."""
    if not _CLEAR_FM2.is_file():
        pytest.skip(f"missing {_CLEAR_FM2}")
    from etalon_build_config import load_etalon_build_config, transition_rooms_from_etalon_build
    from playthrough_build import gameplay_start_frame_from_rows, load_human_playthrough_rows

    rows = load_human_playthrough_rows(mission_m1 / "reference" / "human_playthrough.jsonl")
    gp = gameplay_start_frame_from_rows(
        rows,
        transition_rooms=transition_rooms_from_etalon_build(
            load_etalon_build_config("rushn_attack")
        ),
    )
    probe = probe_movie_playback(
        _CLEAR_FM2,
        resolve_rom("rushn_attack"),
        playback_probe_dir / "clear_staging",
        playback_probe_dir / "clear_probe",
        ram=_ram_addrs(mission_m1),
        probe_at_mf=gp,
        timeout_sec=180.0,
    )
    _assert_gameplay_ram(probe, mf=gp)


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
def test_inference_embed_fm2_ppu_gameplay_at_mf8(
    mission_m1: Path, playback_probe_dir: Path
) -> None:
    """G0: после rebuild inference_cp0 — PPU gameplay @ mf=8 (не title)."""
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
    _assert_ppu_heuristic(probe, title_like=False)


@pytest.fixture
def f0_bench_dir() -> Path:
    path = artifact_quarantine_dir("bench", "fm2_gameplay_capture")
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.mark.requires_fceux
def test_f0_native_record_replay_ram_probe_mf8(
    mission_m1: Path, f0_bench_dir: Path
) -> None:
    """F-proto F0: emulation capture → native record → RAM @ mf=8."""
    if not _INFERENCE_CP0.is_file():
        pytest.skip(f"missing {_INFERENCE_CP0}")
    rom = resolve_rom("rushn_attack")
    out_fm2 = f0_bench_dir / "f0_headless.fm2"
    result = probe_native_record_replay(
        rom,
        out_fm2,
        f0_bench_dir / "headless_record",
        ram=_ram_addrs(mission_m1),
        variant="F0",
        loadstate=_INFERENCE_CP0,
        num_record_frames=60,
        probe_at_mf=8,
        timeout_sec=120.0,
    )
    assert result.get("ok") is True, result
    assert result.get("variant") == "F0", result
    cap = result.get("emulation_capture") or {}
    assert cap.get("ok") is True, result
    assert cap.get("movie_active") is False, result
    assert cap.get("x") == 129, result
    probe = result.get("playback_probe") or {}
    _assert_gameplay_ram(probe, mf=8)
    assert result.get("has_embed") is True, result
    assert (result.get("embed_size") or 0) > 0, result


@pytest.mark.requires_fceux
@pytest.mark.movie_regression
def test_f0_operator_gate(mission_m1: Path, f0_bench_dir: Path) -> None:
    """F-proto F0.5: operator gate — PPU @ mf=8, 28 (GUI window)."""
    if not _INFERENCE_CP0.is_file():
        pytest.skip(f"missing {_INFERENCE_CP0}")
    summary = run_f0_operator_gate(
        resolve_rom("rushn_attack"),
        _INFERENCE_CP0,
        f0_bench_dir,
        ram=_ram_addrs(mission_m1),
        probe_mfs=(8, 28),
        noicon_record=True,
        noicon_visual=False,
        timeout_sec=120.0,
    )
    results_path = Path(summary["results_path"])
    assert results_path.is_file(), summary
    assert summary["verdict"]["ram_pass"] is True, summary
    for mf in ("8", "28"):
        probe = summary["visual"][mf]
        _assert_gameplay_ram(probe, mf=int(mf))
    # Gate-вердикт фиксируется в f0_results.json; PASS/FAIL — по PPU gameplay @ mf=8, 28
    assert "operator_pass" in summary["verdict"], summary
