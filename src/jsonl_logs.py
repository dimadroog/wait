"""JSONL-логи inference: пул поколения logs/<model_version>/."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator


def normalize_model_version(value: str | Path) -> str:
    """Канон model_version = stem (gen1 из gen1.zip / path/to/gen1.zip)."""
    text = str(value).strip()
    if not text:
        raise ValueError("model_version must be non-empty")
    name = Path(text).name
    if name.lower().endswith(".zip"):
        return Path(name).stem
    return name


def resolve_default_model_version(
    mission: Path,
    *,
    model: str | Path | None = None,
    model_version: str | None = None,
) -> str:
    """--model-version → stem(--model) → stem(models/latest.zip); иначе ошибка."""
    if model_version:
        return normalize_model_version(model_version)
    if model is not None:
        return normalize_model_version(model)
    latest = mission / "models" / "latest.zip"
    if latest.is_file():
        try:
            resolved = latest.resolve(strict=False)
            if resolved.name.lower().endswith(".zip") and resolved.stem != "latest":
                return normalize_model_version(resolved)
        except OSError:
            pass
        return "latest"
    raise FileNotFoundError(
        "model_version required: pass --model-version / --model, "
        f"or create {latest}"
    )


def gen_pool_dir(logs_dir: Path, model_version: str, *, mkdir: bool = True) -> Path:
    """logs/<model_version>/ — каталог пула поколения."""
    pool = Path(logs_dir) / normalize_model_version(model_version)
    if mkdir:
        pool.mkdir(parents=True, exist_ok=True)
    return pool


def gen_log_path(
    logs_dir: Path, model_version: str, stem: str, *, mkdir: bool = True
) -> Path:
    """logs/<model_version>/{stem}.jsonl"""
    return gen_pool_dir(logs_dir, model_version, mkdir=mkdir) / f"{stem}.jsonl"


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    if not path.is_file():
        return
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Все строки jsonl (пул поколения = весь файл)."""
    return list(iter_jsonl(path))


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
