"""FM2 playback staging helpers for FCEUX CLI."""
from __future__ import annotations

from pathlib import Path

from fm2_export import PLAYBACK_SAVESTATE_NAME, ensure_savestate_movie_guid, stage_playback_savestate


def stage_playback_fc0(
    inference_fc0: Path,
    staging: Path,
    *,
    guid: str,
    state_name: str = PLAYBACK_SAVESTATE_NAME,
) -> Path:
    """playback.fc0 из inference_cp0 + GUID клипа."""
    staging.mkdir(parents=True, exist_ok=True)
    dest = staging / state_name
    dest.write_bytes(ensure_savestate_movie_guid(inference_fc0.read_bytes(), guid))
    return dest


def fceux_playmovie_argv(
    *,
    staged_fm2: Path,
    staged_rom: Path,
) -> list[str]:
    """Self-contained FM2: -playmovie embed -readonly 1 rom."""
    return [
        "-playmovie",
        staged_fm2.name,
        "-readonly",
        "1",
        staged_rom.name,
    ]


def stage_external_playback(
    staged_fm2: Path,
    staging: Path,
    *,
    fallback_fc0: Path | None = None,
) -> Path:
    """playback.fc0 в staging из embed FM2 (или fallback .fc0)."""
    return stage_playback_savestate(
        staged_fm2,
        staging,
        fallback_fc0=fallback_fc0,
        state_name=PLAYBACK_SAVESTATE_NAME,
    )
