"""Имена tee-логов train и обёртка shell-команды для превью."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from project_paths import repo_root


@dataclass(frozen=True)
class TrainLogSpec:
    train_mode: str
    model_out: str
    model_in: str | None
    timesteps: int
    bc_epochs: int


def sanitize_token(value: object) -> str:
    text = str(value).strip()
    text = text.removesuffix(".zip")
    text = text.replace("--", "")
    text = re.sub(r"[^\w.\-]+", "_", text, flags=re.ASCII)
    text = re.sub(r"_+", "_", text).strip("_")
    return text.lower() or "x"


def build_train_log_basename(spec: TrainLogSpec, *, now: datetime | None = None) -> str:
    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    parts = [
        stamp,
        sanitize_token(Path(spec.model_out).name),
        sanitize_token(spec.train_mode),
    ]
    if spec.train_mode == "from_ancestor" and spec.model_in:
        parts.append(sanitize_token(Path(spec.model_in).name))
    if spec.bc_epochs > 0:
        parts.append(sanitize_token(f"bc_epochs_{spec.bc_epochs}"))
    parts.append(sanitize_token(spec.timesteps))
    return "_".join(parts) + ".log"


def resolve_train_log_path(
    spec: TrainLogSpec,
    *,
    bench_dir: Path | None = None,
    now: datetime | None = None,
) -> Path:
    """Путь tmp/bench/<basename>.log (уникальность через HHMMSS)."""
    directory = bench_dir if bench_dir is not None else repo_root() / "tmp" / "bench"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / build_train_log_basename(spec, now=now)


def shell_with_tee(shell_cmd: str, log_path: Path, *, enabled: bool) -> str:
    if not enabled:
        return shell_cmd
    try:
        rel = log_path.resolve().relative_to(repo_root().resolve()).as_posix()
    except ValueError:
        rel = log_path.as_posix()
    return f"{{ {shell_cmd}; }} 2>&1 | tee {rel}"
