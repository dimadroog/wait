"""Unit tests for FM2 playback staging."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fm2_export import PLAYBACK_SAVESTATE_NAME, fm2_has_embedded_savestate, read_fm2_guid  # noqa: E402
from fm2_export import episode_fm2_guid, export_episode_fm2_from_steps, remap_fm2_guid  # noqa: E402
from fm2_export import refresh_fm2_embedded_savestate  # noqa: E402
from fm2_playback import fceux_playmovie_argv, stage_external_playback, stage_playback_fc0  # noqa: E402

_INFERENCE_CP0 = (
    Path(__file__).resolve().parents[1] / "games" / "rushn_attack" / "missions" / "m1" / "states" / "inference_cp0.fc0"
)


@pytest.fixture
def inference_cp0() -> Path:
    if not _INFERENCE_CP0.is_file():
        pytest.skip(f"missing {_INFERENCE_CP0}")
    return _INFERENCE_CP0


def test_fceux_playmovie_argv_embed_readonly(tmp_path: Path) -> None:
    fm2 = tmp_path / "playback.fm2"
    rom = tmp_path / "rushn_attack"
    fm2.write_text("x\n", encoding="utf-8")
    rom.write_text("x\n", encoding="utf-8")
    argv = fceux_playmovie_argv(staged_fm2=fm2, staged_rom=rom)
    assert argv == [
        "-playmovie",
        "playback.fm2",
        "-readonly",
        "1",
        "rushn_attack",
    ]


def test_stage_playback_fc0_from_inference(tmp_path: Path, inference_cp0: Path) -> None:
    from fm2_export import FCS_MOVIE_GUID_OFFSET, FCS_MOVIE_GUID_LEN, episode_fm2_guid  # noqa: E402

    guid = episode_fm2_guid(salt="direct")
    staged = stage_playback_fc0(inference_cp0, tmp_path, guid=guid)
    assert staged.name == PLAYBACK_SAVESTATE_NAME
    blob = staged.read_bytes()
    assert blob[FCS_MOVIE_GUID_OFFSET : FCS_MOVIE_GUID_OFFSET + FCS_MOVIE_GUID_LEN] == guid.upper().encode("ascii")


def test_stage_external_playback_writes_fc0_keeps_embed(tmp_path: Path, inference_cp0: Path) -> None:
    fm2 = tmp_path / "clip.fm2"
    staging = tmp_path / "staging"
    export_episode_fm2_from_steps(
        [{"action": "right"}],
        fm2,
        save_state_path=inference_cp0,
        episode=2,
    )
    guid = episode_fm2_guid(salt="ext")
    remap_fm2_guid(fm2, guid)
    refresh_fm2_embedded_savestate(fm2, inference_cp0, guid=guid)
    assert fm2_has_embedded_savestate(fm2)

    staged_state = stage_external_playback(fm2, staging, fallback_fc0=inference_cp0)
    assert staged_state.name == PLAYBACK_SAVESTATE_NAME
    assert staged_state.is_file()
    assert fm2_has_embedded_savestate(fm2)
    assert read_fm2_guid(fm2) == guid
