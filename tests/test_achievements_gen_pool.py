"""top_k / deja_vu / new_record считают по пулу файла (поколение)."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from achievements.evaluator import evaluate_attempts_file, evaluate_records  # noqa: E402

_POOL_CONFIG = {
    "nominations": [
        {
            "slug": "episode_reward",
            "idx": 2,
            "type": "top_k",
            "field": "episode_reward",
            "k": 2,
        },
        {
            "slug": "deja_vu",
            "idx": 6,
            "type": "death_cluster",
            "min_count": 3,
        },
        {
            "slug": "new_record",
            "idx": 8,
            "type": "new_max_checkpoint",
        },
    ],
}


def _ts(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_attempts(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")


def test_evaluate_records_top_k_deja_vu_new_record_within_pool() -> None:
    """Базовая логика номинаций на пуле поколения."""
    rows = [
        {
            "episode_id": "a",
            "model_version": "gen0",
            "episode_reward": 10.0,
            "max_checkpoint": 1,
            "timestamp": _ts(datetime(2026, 7, 18, 8, 0, tzinfo=timezone.utc)),
            "died": True,
            "death_room": "0x06",
            "death_x": 160,
        },
        {
            "episode_id": "b",
            "model_version": "gen0",
            "episode_reward": 50.0,
            "max_checkpoint": 2,
            "timestamp": _ts(datetime(2026, 7, 18, 9, 0, tzinfo=timezone.utc)),
            "died": True,
            "death_room": "0x06",
            "death_x": 160,
        },
        {
            "episode_id": "c",
            "model_version": "gen0",
            "episode_reward": 30.0,
            "max_checkpoint": 2,
            "timestamp": _ts(datetime(2026, 7, 18, 10, 0, tzinfo=timezone.utc)),
            "died": True,
            "death_room": "0x06",
            "death_x": 160,
        },
        {
            "episode_id": "d",
            "model_version": "gen0",
            "episode_reward": 5.0,
            "max_checkpoint": 3,
            "timestamp": _ts(datetime(2026, 7, 18, 11, 0, tzinfo=timezone.utc)),
            "died": False,
        },
    ]
    out = {r["episode_id"]: r for r in evaluate_records(rows, _POOL_CONFIG)}

    assert "episode_reward" in out["b"]["tags"]
    assert "episode_reward" in out["c"]["tags"]
    assert "episode_reward" not in out["a"]["tags"]
    assert "episode_reward" not in out["d"]["tags"]

    for eid in ("a", "b", "c"):
        assert "deja_vu" in out[eid]["tags"]
    assert "deja_vu" not in out["d"]["tags"]

    assert "new_record" not in out["a"]["tags"]
    assert "new_record" in out["b"]["tags"]
    assert "new_record" not in out["c"]["tags"]
    assert "new_record" in out["d"]["tags"]


def test_gen_pool_isolation_separate_files(tmp_path: Path) -> None:
    """Другое поколение — другой файл; строки gen1 не влияют на теги gen0."""
    gen0 = tmp_path / "gen0" / "attempts.jsonl"
    gen1 = tmp_path / "gen1" / "attempts.jsonl"
    gen0.parent.mkdir()
    gen1.parent.mkdir()

    _write_attempts(
        gen0,
        [
            {
                "episode_id": "g0_low",
                "model_version": "gen0",
                "episode_reward": 10.0,
                "max_checkpoint": 1,
                "timestamp": _ts(datetime(2026, 7, 18, 8, 0, tzinfo=timezone.utc)),
                "died": True,
                "death_room": "0x06",
                "death_x": 160,
            },
            {
                "episode_id": "g0_high",
                "model_version": "gen0",
                "episode_reward": 40.0,
                "max_checkpoint": 2,
                "timestamp": _ts(datetime(2026, 7, 18, 9, 0, tzinfo=timezone.utc)),
                "died": True,
                "death_room": "0x06",
                "death_x": 160,
            },
        ],
    )
    _write_attempts(
        gen1,
        [
            {
                "episode_id": "g1_top",
                "model_version": "gen1",
                "episode_reward": 999.0,
                "max_checkpoint": 9,
                "timestamp": _ts(datetime(2026, 7, 18, 10, 0, tzinfo=timezone.utc)),
                "died": True,
                "death_room": "0x06",
                "death_x": 160,
            },
            {
                "episode_id": "g1_d2",
                "model_version": "gen1",
                "episode_reward": 1.0,
                "max_checkpoint": 9,
                "timestamp": _ts(datetime(2026, 7, 18, 10, 1, tzinfo=timezone.utc)),
                "died": True,
                "death_room": "0x06",
                "death_x": 160,
            },
            {
                "episode_id": "g1_d3",
                "model_version": "gen1",
                "episode_reward": 1.0,
                "max_checkpoint": 9,
                "timestamp": _ts(datetime(2026, 7, 18, 10, 2, tzinfo=timezone.utc)),
                "died": True,
                "death_room": "0x06",
                "death_x": 160,
            },
        ],
    )

    tagged0 = {r["episode_id"]: r for r in evaluate_attempts_file(gen0, config=_POOL_CONFIG)}
    assert set(tagged0) == {"g0_low", "g0_high"}
    # top_k=2 на двух строках — оба; deja_vu min_count=3 не из gen1
    assert "episode_reward" in tagged0["g0_high"]["tags"]
    assert "episode_reward" in tagged0["g0_low"]["tags"]
    assert "deja_vu" not in tagged0["g0_low"]["tags"]
    assert "deja_vu" not in tagged0["g0_high"]["tags"]

    tagged1 = evaluate_attempts_file(gen1, config=_POOL_CONFIG)
    assert all("deja_vu" in r["tags"] for r in tagged1)


def test_gen_pool_deja_vu_triggers_with_three_deaths(tmp_path: Path) -> None:
    path = tmp_path / "gen0" / "attempts.jsonl"
    path.parent.mkdir()
    rows = []
    for i in range(3):
        rows.append(
            {
                "episode_id": f"d{i}",
                "model_version": "gen0",
                "episode_reward": float(i),
                "max_checkpoint": 0,
                "timestamp": _ts(datetime(2026, 7, 18, 12 + i, tzinfo=timezone.utc)),
                "died": True,
                "death_room": "0x08",
                "death_x": 32,
            }
        )
    _write_attempts(path, rows)
    tagged = evaluate_attempts_file(path, config=_POOL_CONFIG)
    assert all("deja_vu" in r["tags"] for r in tagged)
