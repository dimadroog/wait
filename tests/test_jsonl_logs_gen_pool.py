"""Пул поколения: пути logs/genN/, load без day-cutoff, append без rewrite."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jsonl_logs import (  # noqa: E402
    append_jsonl,
    gen_log_path,
    gen_pool_dir,
    load_jsonl,
    normalize_model_version,
    resolve_default_model_version,
)


def test_normalize_model_version_stem() -> None:
    assert normalize_model_version("gen1") == "gen1"
    assert normalize_model_version("gen1.zip") == "gen1"
    assert normalize_model_version(Path("models/gen0.zip")) == "gen0"
    assert normalize_model_version("runs/gen1_49998_steps.zip") == "gen1_49998_steps"


def test_gen_pool_and_log_path(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    pool = gen_pool_dir(logs, "gen1.zip")
    assert pool == logs / "gen1"
    assert pool.is_dir()
    path = gen_log_path(logs, "gen1", "attempts")
    assert path == logs / "gen1" / "attempts.jsonl"


def test_load_jsonl_keeps_all_rows(tmp_path: Path) -> None:
    path = tmp_path / "attempts.jsonl"
    rows = [
        {"episode_id": "old", "timestamp": "2020-01-01T00:00:00Z"},
        {"episode_id": "new", "timestamp": "2026-07-24T12:00:00Z"},
        {"episode_id": "no_ts"},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    loaded = load_jsonl(path)
    assert [r["episode_id"] for r in loaded] == ["old", "new", "no_ts"]


def test_append_jsonl_does_not_prune(tmp_path: Path) -> None:
    path = tmp_path / "gen0" / "attempts.jsonl"
    append_jsonl(path, {"episode_id": "a"})
    append_jsonl(path, {"episode_id": "b"})
    assert [r["episode_id"] for r in load_jsonl(path)] == ["a", "b"]


def test_resolve_default_model_version(tmp_path: Path) -> None:
    mission = tmp_path
    models = mission / "models"
    models.mkdir()
    (models / "gen1.zip").write_bytes(b"x")
    (models / "latest.zip").write_bytes(b"y")

    assert resolve_default_model_version(mission, model_version="gen0") == "gen0"
    assert resolve_default_model_version(mission, model="gen1.zip") == "gen1"
    # latest.zip is a regular file named latest → stem latest
    assert resolve_default_model_version(mission) == "latest"

    bare = tmp_path / "bare"
    bare.mkdir()
    try:
        resolve_default_model_version(bare)
        raise AssertionError("expected FileNotFoundError")
    except FileNotFoundError:
        pass
