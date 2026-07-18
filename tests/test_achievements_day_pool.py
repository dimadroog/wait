"""top_k / deja_vu / new_record считают только по retention window (день UTC+3)."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from achievements.evaluator import evaluate_attempts_file, evaluate_records  # noqa: E402
from jsonl_logs import retention_cutoff  # noqa: E402

# Минимальный config: только номинации, зависящие от пула.
_POOL_CONFIG = {
    "retention_tz_offset_hours": 3,
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
    """Базовая логика номинаций на уже отфильтрованном пуле."""
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

    # top_k=2 → b (50), c (30)
    assert "episode_reward" in out["b"]["tags"]
    assert "episode_reward" in out["c"]["tags"]
    assert "episode_reward" not in out["a"]["tags"]
    assert "episode_reward" not in out["d"]["tags"]

    # deja_vu: 3 смерти в одном (room, x_bucket=160//16=10)
    for eid in ("a", "b", "c"):
        assert "deja_vu" in out[eid]["tags"]
    assert "deja_vu" not in out["d"]["tags"]

    # new_record: первый cp не тег; рост 1→2 и 2→3 — тег
    assert "new_record" not in out["a"]["tags"]
    assert "new_record" in out["b"]["tags"]
    assert "new_record" not in out["c"]["tags"]  # тот же cp=2
    assert "new_record" in out["d"]["tags"]


def test_day_pool_excludes_prev_day_from_top_k_deja_vu_new_record(tmp_path: Path) -> None:
    """Вчерашние строки в jsonl не входят в пул и не двигают номинации."""
    # mid-day UTC = afternoon UTC+3 on 2026-07-18
    when = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)
    day_start = retention_cutoff(when=when)
    prev = day_start - timedelta(hours=1)
    morning = day_start + timedelta(hours=2)
    noon = day_start + timedelta(hours=6)

    path = tmp_path / "attempts.jsonl"
    _write_attempts(
        path,
        [
            # Вчера: высокий reward, 2 смерти в кластере, высокий cp — не должны влиять
            {
                "episode_id": "yesterday_top",
                "model_version": "gen0",
                "episode_reward": 999.0,
                "max_checkpoint": 9,
                "timestamp": _ts(prev),
                "died": True,
                "death_room": "0x06",
                "death_x": 160,
            },
            {
                "episode_id": "yesterday_death2",
                "model_version": "gen0",
                "episode_reward": 1.0,
                "max_checkpoint": 9,
                "timestamp": _ts(prev + timedelta(minutes=1)),
                "died": True,
                "death_room": "0x06",
                "death_x": 160,
            },
            # Сегодня: только 2 смерти в кластере → без вчера не хватает до min_count=3
            {
                "episode_id": "today_low",
                "model_version": "gen0",
                "episode_reward": 10.0,
                "max_checkpoint": 1,
                "timestamp": _ts(morning),
                "died": True,
                "death_room": "0x06",
                "death_x": 160,
            },
            {
                "episode_id": "today_mid",
                "model_version": "gen0",
                "episode_reward": 40.0,
                "max_checkpoint": 2,
                "timestamp": _ts(noon),
                "died": True,
                "death_room": "0x06",
                "death_x": 160,
            },
            {
                "episode_id": "today_high",
                "model_version": "gen0",
                "episode_reward": 80.0,
                "max_checkpoint": 2,
                "timestamp": _ts(noon + timedelta(minutes=30)),
                "died": False,
            },
        ],
    )

    tagged = evaluate_attempts_file(path, config=_POOL_CONFIG, when=when)
    by_id = {r["episode_id"]: r for r in tagged}

    assert set(by_id) == {"today_low", "today_mid", "today_high"}

    # top_k=2 среди дневного пула: today_high (80), today_mid (40) — не yesterday_top
    assert "episode_reward" in by_id["today_high"]["tags"]
    assert "episode_reward" in by_id["today_mid"]["tags"]
    assert "episode_reward" not in by_id["today_low"]["tags"]

    # deja_vu: 2 сегодняшние смерти < 3; вчерашние не досчитывают
    assert "deja_vu" not in by_id["today_low"]["tags"]
    assert "deja_vu" not in by_id["today_mid"]["tags"]

    # new_record: baseline дня с cp=1; рост до 2 → тег; вчерашний cp=9 не baseline
    assert "new_record" not in by_id["today_low"]["tags"]
    assert "new_record" in by_id["today_mid"]["tags"]
    assert "new_record" not in by_id["today_high"]["tags"]


def test_day_pool_deja_vu_triggers_with_three_same_day_deaths(tmp_path: Path) -> None:
    when = datetime(2026, 7, 18, 14, 0, tzinfo=timezone.utc)
    day_start = retention_cutoff(when=when)
    path = tmp_path / "attempts.jsonl"
    rows = []
    for i in range(3):
        rows.append(
            {
                "episode_id": f"d{i}",
                "model_version": "gen0",
                "episode_reward": float(i),
                "max_checkpoint": 0,
                "timestamp": _ts(day_start + timedelta(hours=1 + i)),
                "died": True,
                "death_room": "0x08",
                "death_x": 32,
            }
        )
    _write_attempts(path, rows)

    tagged = evaluate_attempts_file(path, config=_POOL_CONFIG, when=when)
    assert all("deja_vu" in r["tags"] for r in tagged)
