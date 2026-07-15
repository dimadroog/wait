"""Preflight cleanup перед inference (запись) и эфирным replay."""
from __future__ import annotations

import shutil
from pathlib import Path

from jsonl_logs import utc_date_prefix
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
    """Удалить inference-артефакты за UTC-день (attempts, FM2, playlist)."""
    if not logs_dir.is_dir():
        return []
    prefix = date_prefix or utc_date_prefix()
    removed: list[Path] = []
    for path in sorted(logs_dir.iterdir()):
        if not path.name.startswith(prefix):
            continue
        if path.name == ".gitkeep":
            continue
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
        removed.append(path)
    return removed


def require_inference_preflight(
    *,
    game: str = "rushn_attack",
    mission: str = "m1",
    clean_logs: bool = True,
    label: str = "inference_preflight",
) -> None:
    """Очистка перед записью inference: logs (опц.), play_fm2 staging, bridge IPC, orphan FCEUX."""
    cleanup_play_fm2_staging()
    if clean_logs:
        logs_dir = mission_dir(game, mission) / "logs"
        removed = cleanup_inference_logs(logs_dir)
        if removed:
            print(f"preflight [{label}]: removed {len(removed)} log artifact(s) under {logs_dir}")
    require_clean_preflight(label=label, prefixes=INFERENCE_BRIDGE_PREFIXES)


def require_playback_preflight(*, label: str = "playback_preflight") -> None:
    """Очистка перед play_inference_fm2: staging + bridge, без wipe logs/."""
    cleanup_play_fm2_staging()
    require_clean_preflight(label=label, prefixes=INFERENCE_BRIDGE_PREFIXES)
