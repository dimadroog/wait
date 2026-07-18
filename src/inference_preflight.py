"""Preflight cleanup перед inference (запись) и эфирным replay."""
from __future__ import annotations

import shutil
from pathlib import Path

from achievements.airtime import load_day_playlist_airtime
from jsonl_logs import retention_date_prefix
from project_paths import mission_dir, repo_root
from train.env_factory import require_clean_preflight

INFERENCE_BRIDGE_PREFIXES = ("inference", "train_", "bench_")


def cleanup_play_fm2_staging() -> None:
    staging = repo_root() / "tmp" / "play_fm2" / "staging"
    if staging.is_dir():
        shutil.rmtree(staging, ignore_errors=True)


def cleanup_inference_logs(
    logs_dir: Path,
    *,
    date_prefix: str | None = None,
) -> list[Path]:
    """Удалить inference-артефакты за день retention (logs/YYYYMMDD/ + legacy YYYYMMDD_*)."""
    if not logs_dir.is_dir():
        return []
    prefix = date_prefix or retention_date_prefix()
    removed: list[Path] = []
    day_dir = logs_dir / prefix
    if day_dir.is_dir():
        shutil.rmtree(day_dir, ignore_errors=True)
        removed.append(day_dir)
    # Legacy flat layout: logs/YYYYMMDD_*.jsonl / .fm2 / playlist
    for path in sorted(logs_dir.iterdir()):
        if path.name == ".gitkeep":
            continue
        if path.name == prefix or not path.name.startswith(f"{prefix}_"):
            continue
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
        removed.append(path)
    return removed


def day_logs_dir(logs_dir: Path, *, date_prefix: str | None = None) -> Path:
    """Путь logs/YYYYMMDD/ за текущий retention-день (без mkdir)."""
    prefix = date_prefix or retention_date_prefix()
    return logs_dir / prefix


def report_day_airtime(
    logs_dir: Path,
    *,
    date_prefix: str | None = None,
    label: str = "preflight",
) -> float:
    """Напечатать текущий airtime дня; вернуть hours (0 если плейлиста нет)."""
    day_dir = day_logs_dir(logs_dir, date_prefix=date_prefix)
    air = load_day_playlist_airtime(day_dir) if day_dir.is_dir() else None
    if air is None:
        print(
            f"preflight [{label}]: keep day logs ({day_dir.name}); "
            f"airtime=0s (no playlist.json yet)",
            flush=True,
        )
        return 0.0
    print(
        f"preflight [{label}]: keep day logs ({day_dir.name}); "
        f"airtime={air.seconds:.1f}s ({air.hours:.4f}h), clips={air.clip_count}",
        flush=True,
    )
    return air.hours


def warn_portable_movies_pollution(*, label: str = "preflight") -> None:
    """FCEUX путает FM2 с одинаковым romChecksum в fceux/portable/movies/."""
    movies = repo_root() / "fceux" / "portable" / "movies"
    if not movies.is_dir():
        return
    stray = sorted(movies.glob("*.fm2"))
    if not stray:
        return
    names = ", ".join(p.name for p in stray)
    print(
        f"preflight [{label}]: WARNING {movies.as_posix()} contains FM2 ({names}); "
        "FCEUX may show wrong movie — remove game FM2 from portable/movies/",
        flush=True,
    )


def require_inference_preflight(
    *,
    game: str = "rushn_attack",
    mission: str = "m1",
    clean_logs: bool = False,
    label: str = "inference_preflight",
) -> None:
    """Перед inference: staging/bridge; logs дня по умолчанию сохраняются.

    clean_logs=True — опциональный wipe logs/YYYYMMDD/ перед сбором.
    При keep — печатает текущий airtime дня (для remaining target).
    """
    cleanup_play_fm2_staging()
    warn_portable_movies_pollution(label=label)
    logs_dir = mission_dir(game, mission) / "logs"
    if clean_logs:
        removed = cleanup_inference_logs(logs_dir)
        if removed:
            print(
                f"preflight [{label}]: wiped {len(removed)} log artifact(s) under {logs_dir}",
                flush=True,
            )
        else:
            print(f"preflight [{label}]: wipe day logs (nothing to remove)", flush=True)
    else:
        report_day_airtime(logs_dir, label=label)
    require_clean_preflight(label=label, prefixes=INFERENCE_BRIDGE_PREFIXES)


def require_playback_preflight(*, label: str = "playback_preflight") -> None:
    """Очистка перед play_inference_fm2: staging + bridge, без wipe logs/."""
    cleanup_play_fm2_staging()
    warn_portable_movies_pollution(label=label)
    require_clean_preflight(label=label, prefixes=INFERENCE_BRIDGE_PREFIXES)
