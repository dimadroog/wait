"""Unit tests for FM2 export and embedded savestate."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fm2_export import (  # noqa: E402
    build_fm2_header,
    default_fm2_template,
    export_episode_fm2_from_steps,
    fc0_to_savestate_hex,
    fm2_has_embedded_savestate,
    patch_savestate_movie_guid,
    read_fm2_guid,
)
from fm2_export import INFERENCE_FM2_GUID  # noqa: E402

_MISSION = Path(__file__).resolve().parents[1] / "games" / "rushn_attack" / "missions" / "m1"
_INFERENCE_CP0 = _MISSION / "states" / "inference_cp0.fc0"
_CLEAR_GUID = "A8C431C3-A298-2CE5-5493-21BB5AEAE61F"


@pytest.fixture
def inference_cp0() -> Path:
    if not _INFERENCE_CP0.is_file():
        pytest.skip(f"missing {_INFERENCE_CP0}")
    return _INFERENCE_CP0


def test_patch_savestate_movie_guid(inference_cp0: Path) -> None:
    blob = inference_cp0.read_bytes()
    patched = patch_savestate_movie_guid(blob, INFERENCE_FM2_GUID)
    assert _CLEAR_GUID.encode() not in patched
    assert INFERENCE_FM2_GUID.encode() in patched
    # idempotent
    again = patch_savestate_movie_guid(patched, INFERENCE_FM2_GUID)
    assert again == patched


def test_fc0_to_savestate_hex_prefix(inference_cp0: Path) -> None:
    hex_val = fc0_to_savestate_hex(inference_cp0, target_guid=INFERENCE_FM2_GUID)
    assert hex_val.startswith("0x")
    assert len(hex_val) == 2 + inference_cp0.stat().st_size * 2


def test_build_fm2_header_embeds_savestate(inference_cp0: Path) -> None:
    template = default_fm2_template("rushn_attack")
    header = build_fm2_header(
        template,
        embed_savestate=True,
        save_state_path=inference_cp0,
    )
    # no length key (FM3 guard)
    assert not any(line.startswith("length ") for line in header)
    guid_lines = [line for line in header if line.startswith("guid ")]
    save_lines = [line for line in header if line.startswith("savestate ")]
    assert len(guid_lines) == 1
    assert guid_lines[0] == f"guid {INFERENCE_FM2_GUID}"
    assert len(save_lines) == 1
    assert save_lines[0].startswith("savestate 0x")


def test_export_episode_fm2_embedded(tmp_path: Path, inference_cp0: Path) -> None:
    out = tmp_path / "ep.fm2"
    steps = [{"action": "right"}, {"action": ""}]
    export_episode_fm2_from_steps(
        steps,
        out,
        save_state_path=inference_cp0,
    )
    assert fm2_has_embedded_savestate(out)
    assert read_fm2_guid(out) == INFERENCE_FM2_GUID
    sidecar = out.with_suffix(".overlay.json")
    assert not sidecar.is_file()


def test_embed_export_timing_and_size(inference_cp0: Path, tmp_path: Path) -> None:
    """Замер на типичном inference_cp0.fc0 (BACKLOG 3.1)."""
    out = tmp_path / "bench.fm2"
    t0 = time.perf_counter()
    export_episode_fm2_from_steps(
        [{"action": "right"}],
        out,
        save_state_path=inference_cp0,
    )
    elapsed = time.perf_counter() - t0
    fm2_size = out.stat().st_size
    # ~97 KiB state → ~195 KiB hex + header; экспорт должен быть быстрым
    assert fm2_size > inference_cp0.stat().st_size
    assert elapsed < 2.0, f"embed export too slow: {elapsed:.2f}s"
    print(f"embed export: {fm2_size} bytes in {elapsed*1000:.1f} ms")
