"""Preflight cleanup перед inference (запись) и GUI replay."""
from __future__ import annotations

import shutil
from pathlib import Path

from jsonl_logs import gen_pool_dir, normalize_model_version, resolve_default_model_version
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
    model_version: str,
) -> list[Path]:
    """Удалить inference-артефакты пула поколения logs/<model_version>/."""
    if not logs_dir.is_dir():
        return []
    version = normalize_model_version(model_version)
    removed: list[Path] = []
    pool_dir = logs_dir / version
    if pool_dir.is_dir():
        shutil.rmtree(pool_dir, ignore_errors=True)
        removed.append(pool_dir)
    return removed


def gen_logs_dir(logs_dir: Path, *, model_version: str) -> Path:
    """Путь logs/<model_version>/ (без mkdir)."""
    return gen_pool_dir(logs_dir, model_version, mkdir=False)


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
    game: str,
    mission: str,
    model_version: str | None = None,
    model: str | None = None,
    clean_logs: bool = False,
    label: str = "inference_preflight",
) -> str:
    """Перед inference: staging/bridge; пул gen по умолчанию сохраняется.

    clean_logs=True — опциональный wipe logs/<model_version>/ перед сбором.
    Возвращает канонический model_version.
    """
    cleanup_play_fm2_staging()
    warn_portable_movies_pollution(label=label)
    mission_path = mission_dir(game, mission)
    version = resolve_default_model_version(
        mission_path, model=model, model_version=model_version
    )
    logs_dir = mission_path / "logs"
    if clean_logs:
        removed = cleanup_inference_logs(logs_dir, model_version=version)
        if removed:
            print(
                f"preflight [{label}]: wiped {len(removed)} log artifact(s) under {logs_dir}",
                flush=True,
            )
        else:
            print(
                f"preflight [{label}]: wipe gen logs ({version}) (nothing to remove)",
                flush=True,
            )
    else:
        pool_dir = gen_logs_dir(logs_dir, model_version=version)
        print(
            f"preflight [{label}]: keep gen logs ({pool_dir.name})",
            flush=True,
        )
    require_clean_preflight(label=label, prefixes=INFERENCE_BRIDGE_PREFIXES)
    return version


def require_playback_preflight(*, label: str = "playback_preflight") -> None:
    """Очистка перед play_inference_fm2: staging + bridge, без wipe logs/."""
    cleanup_play_fm2_staging()
    warn_portable_movies_pollution(label=label)
    require_clean_preflight(label=label, prefixes=INFERENCE_BRIDGE_PREFIXES)
