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


def require_consistent_model_version(
    *,
    model: str | Path | None = None,
    model_version: str | None = None,
) -> None:
    """G3: --model и --model-version с разным stem → SystemExit."""
    if model is None or not model_version:
        return
    stem_model = normalize_model_version(model)
    stem_version = normalize_model_version(model_version)
    if stem_model != stem_version:
        raise SystemExit(
            f"--model stem {stem_model!r} != --model-version {stem_version!r}; "
            "уберите один флаг или выровняйте имена (иначе logs/genN/ чужой)"
        )


from project_paths import default_model_zip
from train.checkpointing import latest_checkpoint_path


def resolve_default_model_version(
    mission: Path,
    *,
    model: str | Path | None = None,
    model_version: str | None = None,
) -> str:
    """--model-version → stem(--model) → default genN.zip / genN.latest.zip."""
    require_consistent_model_version(model=model, model_version=model_version)
    if model_version:
        return normalize_model_version(model_version)
    if model is not None:
        return normalize_model_version(model)
    canonical = default_model_zip(mission)
    if canonical.is_file():
        return normalize_model_version(canonical)
    latest = latest_checkpoint_path(canonical)
    if latest.is_file():
        return normalize_model_version(canonical)
    raise FileNotFoundError(
        "model_version required: pass --model-version / --model, "
        f"or create {canonical}"
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


def next_episode_number(attempts_path: Path) -> int:
    """Следующий номер попытки в пуле поколения (max(episode)+1; пустой пул → 1).

    При keep-логах нумерация не должна сбрасываться: иначе несколько прогонов
    делят episode=1 и export/playlist склеивают чужие сегменты.
    """
    if not attempts_path.is_file():
        return 1
    max_ep = 0
    for row in iter_jsonl(attempts_path):
        try:
            max_ep = max(max_ep, int(row.get("episode", 0) or 0))
        except (TypeError, ValueError):
            continue
    return max_ep + 1
