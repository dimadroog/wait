"""--target-airtime: parse + pad добирает клипы до N секунд."""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from achievements.airtime import (  # noqa: E402
    DEFAULT_TARGET_AIRTIME_HOURS,
    measure_playlist_airtime,
    parse_airtime_hours,
)
from achievements.playlist import build_playlist  # noqa: E402
from jsonl_logs import utc_date_prefix  # noqa: E402
from project_paths import repo_root  # noqa: E402


def test_parse_airtime_hours_units() -> None:
    assert parse_airtime_hours(1) == 1.0
    assert parse_airtime_hours("1h") == 1.0
    assert parse_airtime_hours("30m") == 0.5
    assert parse_airtime_hours("90s") == 90 / 3600.0
    assert parse_airtime_hours(DEFAULT_TARGET_AIRTIME_HOURS) == 1.0
    with pytest.raises(ValueError):
        parse_airtime_hours(0)
    with pytest.raises(ValueError):
        parse_airtime_hours("-1h")


def _minimal_top1_config() -> dict:
    return {
        "broadcast_order": ["episode_reward"],
        "nominations": [
            {
                "idx": 2,
                "slug": "episode_reward",
                "title": "Greedy",
                "label": "Greedy",
                "tier": "gold",
                "type": "top_k",
                "field": "episode_reward",
                "k": 1,
                "order": "desc",
            }
        ],
    }


def test_build_playlist_pad_reaches_target_seconds() -> None:
    logs = repo_root() / "tmp" / "smoke" / "playlist_pad_airtime" / "logs"
    if logs.exists():
        shutil.rmtree(logs)
    day = logs / utc_date_prefix()
    day.mkdir(parents=True)

    inputs_lines: list[str] = []
    attempts_lines: list[str] = []
    # 4 эпизода × ~4 step → короткие FM2; top_k=1 возьмёт один, pad доберёт остальные
    for ep in range(1, 5):
        for step in range(4):
            inputs_lines.append(
                json.dumps({"episode": ep, "step": step, "frame": step, "action": "right"})
            )
        attempts_lines.append(
            json.dumps(
                {
                    "episode": ep,
                    "episode_reward": float(100 - ep),
                    "episode_frames": 4,
                    "max_checkpoint": 1,
                    "died": False,
                    "tags": ["episode_reward"] if ep == 1 else [],
                    "inference_inputs_ref": "inference_inputs.jsonl",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
        )
    inputs = day / "inference_inputs.jsonl"
    attempts = day / "attempts.jsonl"
    inputs.write_text("\n".join(inputs_lines) + "\n", encoding="utf-8")
    attempts.write_text("\n".join(attempts_lines) + "\n", encoding="utf-8")

    # Один клип ≈ (4 + hold180)/60 ≈ 3s; target 8s → pad добирает ещё эпизоды
    created, manifest_path, clip_count = build_playlist(
        attempts,
        logs,
        config=_minimal_top1_config(),
        inference_inputs_path=inputs,
        game="rushn_attack",
        mission="m1",
        pad_to_seconds=8.0,
    )
    assert manifest_path and manifest_path.is_file()
    assert clip_count >= 3
    assert "pad" in created
    air = measure_playlist_airtime(manifest_path)
    assert air.seconds + 1e-6 >= 8.0
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert any(c.get("slug") == "pad" for c in manifest["clips"])
    assert manifest["airtime"]["seconds"] + 1e-6 >= 8.0
