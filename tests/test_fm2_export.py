"""Unit tests for FM2 export and embedded savestate."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fm2_export import (  # noqa: E402
    PLAYBACK_SAVESTATE_NAME,
    build_fm2_header,
    default_fm2_template,
    ensure_savestate_movie_guid,
    export_episode_fm2_from_steps,
    fc0_to_savestate_hex,
    fm2_has_embedded_savestate,
    patch_savestate_movie_guid,
    read_embedded_savestate_blob,
    read_fm2_guid,
    refresh_fm2_embedded_savestate,
    stage_playback_savestate,
)
from fm2_export import INFERENCE_FM2_GUID  # noqa: E402
from fm2_export import episode_fm2_guid  # noqa: E402
from fm2_export import remap_fm2_guid  # noqa: E402

_MISSION = Path(__file__).resolve().parents[1] / "games" / "rushn_attack" / "missions" / "m1"
_INFERENCE_CP0 = _MISSION / "save_states" / "inference_cp0.fc0"
_CLEAR_GUID = "A8C431C3-A298-2CE5-5493-21BB5AEAE61F"


@pytest.fixture
def inference_cp0() -> Path:
    if not _INFERENCE_CP0.is_file():
        pytest.skip(f"missing {_INFERENCE_CP0}")
    return _INFERENCE_CP0


def test_patch_savestate_movie_guid(inference_cp0: Path) -> None:
    blob = inference_cp0.read_bytes()
    patched = ensure_savestate_movie_guid(blob, INFERENCE_FM2_GUID)
    from fm2_export import FCS_MOVIE_GUID_OFFSET, _GUID_BYTES_RE

    assert patched[FCS_MOVIE_GUID_OFFSET : FCS_MOVIE_GUID_OFFSET + 36] == INFERENCE_FM2_GUID.encode()
    assert len(list(_GUID_BYTES_RE.finditer(patched))) == 1
    again = ensure_savestate_movie_guid(patched, INFERENCE_FM2_GUID)
    assert again == patched


def test_fc0_to_savestate_hex_prefix(inference_cp0: Path) -> None:
    hex_val = fc0_to_savestate_hex(inference_cp0, target_guid=INFERENCE_FM2_GUID)
    assert hex_val.startswith("0x")
    assert len(hex_val) == 2 + inference_cp0.stat().st_size * 2


def test_inference_guid_differs_from_reference_template() -> None:
    template = default_fm2_template("rushn_attack", "m1")
    assert template.name == "header.fm2"
    assert "reference" in template.as_posix()
    template_guid = read_fm2_guid(template)
    assert template_guid is not None
    assert INFERENCE_FM2_GUID != template_guid


def test_default_fm2_template_not_in_portable() -> None:
    template = default_fm2_template("rushn_attack", "m1")
    assert "fceux/portable/movies" not in template.as_posix()


def test_build_fm2_header_embeds_savestate(inference_cp0: Path) -> None:
    template = default_fm2_template("rushn_attack", "m1")
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


def test_episode_fm2_guid_unique_per_episode() -> None:
    g1 = episode_fm2_guid(1)
    g2 = episode_fm2_guid(2)
    assert g1 != g2
    assert g1 != INFERENCE_FM2_GUID
    assert g2 != INFERENCE_FM2_GUID


def test_remap_fm2_guid_changes_header_and_savestate(tmp_path: Path, inference_cp0: Path) -> None:
    from fm2_export import export_episode_fm2_from_steps, read_fm2_guid, remap_fm2_guid

    src = tmp_path / "src.fm2"
    export_episode_fm2_from_steps(
        [{"action": "right"}],
        src,
        save_state_path=inference_cp0,
        episode=1,
    )
    old = read_fm2_guid(src)
    new = episode_fm2_guid(salt="playback-test")
    assert remap_fm2_guid(src, new) == old
    assert read_fm2_guid(src) == new


def test_export_episode_fm2_embedded(tmp_path: Path, inference_cp0: Path) -> None:
    out = tmp_path / "ep.fm2"
    steps = [{"action": "right"}, {"action": ""}]
    export_episode_fm2_from_steps(
        steps,
        out,
        save_state_path=inference_cp0,
        episode=7,
    )
    assert fm2_has_embedded_savestate(out)
    assert read_fm2_guid(out) == episode_fm2_guid(7)
    sidecar = out.with_suffix(".overlay.json")
    assert not sidecar.is_file()


def test_read_embedded_savestate_blob(tmp_path: Path, inference_cp0: Path) -> None:
    out = tmp_path / "ep.fm2"
    export_episode_fm2_from_steps(
        [{"action": "right"}],
        out,
        save_state_path=inference_cp0,
        episode=3,
    )
    blob = read_embedded_savestate_blob(out)
    assert blob is not None
    assert len(blob) == inference_cp0.stat().st_size


def test_stage_playback_savestate_from_embed(tmp_path: Path, inference_cp0: Path) -> None:
    fm2 = tmp_path / "clip.fm2"
    staging = tmp_path / "staging"
    export_episode_fm2_from_steps(
        [{"action": "right"}],
        fm2,
        save_state_path=inference_cp0,
        episode=5,
    )
    remap_fm2_guid(fm2, episode_fm2_guid(salt="stage-test"))
    staged = stage_playback_savestate(fm2, staging)
    assert staged.name == PLAYBACK_SAVESTATE_NAME
    assert staged.parent == staging
    assert staged.read_bytes() == read_embedded_savestate_blob(fm2)


def test_stage_playback_savestate_fallback_patches_guid(
    tmp_path: Path, inference_cp0: Path
) -> None:
    """Без embed — fallback inference_cp0 с GUID клипа."""
    from fm2_export import build_fm2_header, default_fm2_template

    fm2 = tmp_path / "no_embed.fm2"
    guid = episode_fm2_guid(salt="fallback")
    header = build_fm2_header(default_fm2_template("rushn_attack", "m1"), guid=guid)
    fm2.write_text("\n".join(header + ["|0|........|........||"]) + "\n", encoding="utf-8")
    staging = tmp_path / "staging"
    staged = stage_playback_savestate(fm2, staging, fallback_fc0=inference_cp0)
    assert staged.is_file()
    assert read_embedded_savestate_blob(fm2) is None
    patched = patch_savestate_movie_guid(inference_cp0.read_bytes(), guid)
    from fm2_export import _GUID_BYTES_RE

    if list(_GUID_BYTES_RE.finditer(inference_cp0.read_bytes())):
        assert staged.read_bytes() == patched
    else:
        assert staged.read_bytes() == inference_cp0.read_bytes()


def test_remap_fm2_guid_injects_missing_blob_guid(tmp_path: Path, inference_cp0: Path) -> None:
    from fm2_export import FCS_MOVIE_GUID_OFFSET, _GUID_BYTES_RE, read_embedded_savestate_blob

    src = tmp_path / "src.fm2"
    export_episode_fm2_from_steps(
        [{"action": "right"}],
        src,
        save_state_path=inference_cp0,
        episode=1,
    )
    new = episode_fm2_guid(salt="inject-test")
    remap_fm2_guid(src, new)
    blob = read_embedded_savestate_blob(src)
    assert blob is not None
    assert blob[FCS_MOVIE_GUID_OFFSET : FCS_MOVIE_GUID_OFFSET + 36] == new.encode()
    assert len(list(_GUID_BYTES_RE.finditer(blob))) == 1


def test_refresh_fm2_embedded_savestate_from_inference_cp0(
    tmp_path: Path, inference_cp0: Path
) -> None:
    from fm2_export import FCS_MOVIE_GUID_OFFSET, export_episode_fm2_from_steps, refresh_fm2_embedded_savestate

    fm2 = tmp_path / "old.fm2"
    export_episode_fm2_from_steps(
        [{"action": "right"}],
        fm2,
        save_state_path=inference_cp0,
        episode=9,
    )
    # Симуляция старого лога: embed без GUID в blob.
    lines = fm2.read_text(encoding="utf-8").splitlines()
    fm2.write_text(
        "\n".join(line for line in lines if not line.startswith("savestate ")) + "\n",
        encoding="utf-8",
    )
    assert read_embedded_savestate_blob(fm2) is None
    clip_guid = episode_fm2_guid(salt="refresh-test")
    remap_fm2_guid(fm2, clip_guid)
    refresh_fm2_embedded_savestate(fm2, inference_cp0, guid=clip_guid)
    blob = read_embedded_savestate_blob(fm2)
    assert blob is not None
    assert blob[FCS_MOVIE_GUID_OFFSET : FCS_MOVIE_GUID_OFFSET + 36] == clip_guid.encode()
    assert len(blob) == inference_cp0.stat().st_size


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
