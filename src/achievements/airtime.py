"""Оценка airtime плейлиста: Σ (fm2_frames + hold) / 60 (realtime NES)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from project_paths import count_fm2_frames

NES_FPS = 60.0
DEFAULT_HOLD_FRAMES = 180  # show_until_frame / hold между клипами (как play_inference_fm2)
DEFAULT_FRAME_SKIP = 4  # fm2_frames ≈ episode_frames × frame_skip
DEFAULT_TARGET_AIRTIME_HOURS = 1.0


@dataclass(frozen=True)
class ClipAirtime:
    fm2: str
    fm2_frames: int
    hold_frames: int

    @property
    def total_frames(self) -> int:
        return self.fm2_frames + self.hold_frames

    @property
    def seconds(self) -> float:
        return frames_to_seconds(self.total_frames)


@dataclass(frozen=True)
class PlaylistAirtime:
    clips: tuple[ClipAirtime, ...]

    @property
    def clip_count(self) -> int:
        return len(self.clips)

    @property
    def total_fm2_frames(self) -> int:
        return sum(c.fm2_frames for c in self.clips)

    @property
    def total_hold_frames(self) -> int:
        return sum(c.hold_frames for c in self.clips)

    @property
    def total_frames(self) -> int:
        return self.total_fm2_frames + self.total_hold_frames

    @property
    def seconds(self) -> float:
        return frames_to_seconds(self.total_frames)

    @property
    def hours(self) -> float:
        return self.seconds / 3600.0

    def as_dict(self) -> dict[str, Any]:
        """Компактная сводка для playlist.json → airtime."""
        return {
            "seconds": round(self.seconds, 3),
            "hours": round(self.hours, 6),
            "total_fm2_frames": self.total_fm2_frames,
            "total_hold_frames": self.total_hold_frames,
            "clip_count": self.clip_count,
            "nes_fps": NES_FPS,
            "formula": "sum(fm2_frames + hold_frames) / nes_fps",
        }


def frames_to_seconds(frames: int | float, *, nes_fps: float = NES_FPS) -> float:
    return float(frames) / float(nes_fps)


def parse_airtime_hours(value: str | float | int) -> float:
    """Часы airtime: `1`, `1h`, `30m`, `90s` → float hours (>0)."""
    if isinstance(value, (int, float)):
        hours = float(value)
    else:
        raw = str(value).strip().lower().replace(" ", "")
        if not raw:
            raise ValueError("empty airtime value")
        match = re.fullmatch(r"([0-9]*\.?[0-9]+)([hms]?)", raw)
        if not match:
            raise ValueError(f"invalid airtime value: {value!r}")
        amount = float(match.group(1))
        unit = match.group(2) or "h"
        if unit == "h":
            hours = amount
        elif unit == "m":
            hours = amount / 60.0
        else:
            hours = amount / 3600.0
    if hours <= 0:
        raise ValueError(f"airtime must be > 0, got {hours}")
    return hours


def load_playlist_airtime(pool_dir: Path) -> PlaylistAirtime | None:
    """Airtime из pool_dir/playlist.json или None, если манифеста нет."""
    path = pool_dir / "playlist.json"
    if not path.is_file():
        return None
    return measure_playlist_airtime(path, logs_dir=pool_dir)


def estimate_fm2_frames(
    episode_frames: int,
    *,
    frame_skip: int = DEFAULT_FRAME_SKIP,
) -> int:
    """Оценка NES-кадров клипа до экспорта FM2: episode_frames × frame_skip."""
    return max(0, int(episode_frames) * int(frame_skip))


def estimate_clip_airtime_seconds(
    episode_frames: int,
    *,
    frame_skip: int = DEFAULT_FRAME_SKIP,
    hold_frames: int = DEFAULT_HOLD_FRAMES,
) -> float:
    return frames_to_seconds(estimate_fm2_frames(episode_frames, frame_skip=frame_skip) + hold_frames)


def overlay_hold_frames(
    overlay_path: Path | None,
    *,
    default: int = DEFAULT_HOLD_FRAMES,
) -> int:
    if not overlay_path or not overlay_path.is_file():
        return default
    try:
        payload = json.loads(overlay_path.read_text(encoding="utf-8"))
        return int(payload.get("show_until_frame", default))
    except (json.JSONDecodeError, TypeError, ValueError, OSError):
        return default


def _resolve_clip_fm2(logs_dir: Path, fm2_name: str) -> Path:
    name = Path(fm2_name).name
    candidate = logs_dir / name
    if candidate.is_file():
        return candidate
    legacy = logs_dir / fm2_name
    if legacy.is_file():
        return legacy
    raise FileNotFoundError(f"Playlist FM2 not found: {fm2_name} under {logs_dir}")


def measure_playlist_airtime(
    playlist: Path | dict[str, Any],
    *,
    logs_dir: Path | None = None,
    default_hold: int = DEFAULT_HOLD_FRAMES,
) -> PlaylistAirtime:
    """Airtime из playlist.json + соседних .fm2 / .overlay.json.

    Формула (как timeout в play_inference_fm2): Σ (fm2_frames + hold) / 60,
    hold = overlay.show_until_frame (дефолт 180) на каждый клип, включая последний.
    """
    if isinstance(playlist, Path):
        playlist_path = playlist
        data = json.loads(playlist_path.read_text(encoding="utf-8"))
        base = logs_dir or playlist_path.parent
    else:
        data = playlist
        if logs_dir is None:
            raise ValueError("logs_dir required when playlist is a dict")
        base = logs_dir

    clips_out: list[ClipAirtime] = []
    for clip in data.get("clips") or []:
        fm2_name = clip.get("fm2") or clip.get("fm2_path")
        if not fm2_name:
            raise ValueError(f"Clip missing fm2: {clip}")
        fm2_path = _resolve_clip_fm2(base, str(fm2_name))
        fm2_frames = count_fm2_frames(fm2_path)

        overlay_name = clip.get("overlay")
        if overlay_name:
            overlay_path = base / Path(str(overlay_name)).name
        else:
            overlay_path = fm2_path.with_suffix(".overlay.json")
        hold = overlay_hold_frames(overlay_path if overlay_path.is_file() else None, default=default_hold)

        clips_out.append(
            ClipAirtime(
                fm2=fm2_path.name,
                fm2_frames=fm2_frames,
                hold_frames=hold,
            )
        )

    return PlaylistAirtime(clips=tuple(clips_out))
