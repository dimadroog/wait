"""Editorial playlist: лимиты airtime/clips."""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from achievements.airtime import measure_playlist_airtime  # noqa: E402
from achievements.playlist import build_playlist  # noqa: E402
from project_paths import repo_root  # noqa: E402

_GEN = "gen0"


def _editorial_config() -> dict:
    return {
        "broadcast_order": ["episode_reward", "fastest_death"],
        "editorial_order": ["episode_reward"],
        "editorial": {"max_airtime": "30s", "max_clips": 2, "max_per_slug": 1},
        "nominations": [
            {
                "idx": 2,
                "slug": "episode_reward",
                "title": "Greedy",
                "label": "Greedy",
                "tier": "gold",
                "type": "top_k",
                "field": "episode_reward",
                "k": 3,
                "order": "desc",
            },
            {
                "idx": 8,
                "slug": "fastest_death",
                "title": "Instant",
                "label": "Instant",
                "tier": "skull",
                "type": "instant",
                "condition": {"died": True, "max_episode_frames": 99},
            },
        ],
    }


def test_editorial_playlist_respects_max_clips() -> None:
    logs = repo_root() / "tmp" / "smoke" / "editorial_playlist" / "logs"
    if logs.exists():
        shutil.rmtree(logs)
    day = logs / _GEN
    day.mkdir(parents=True)

    inputs_lines: list[str] = []
    attempts_lines: list[str] = []
    for ep in range(1, 6):
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
                    "died": True,
                    "death_room": "0x08",
                    "model_version": _GEN,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
        )
    inputs = day / "inference_inputs.jsonl"
    attempts = day / "attempts.jsonl"
    inputs.write_text("\n".join(inputs_lines) + "\n", encoding="utf-8")
    attempts.write_text("\n".join(attempts_lines) + "\n", encoding="utf-8")

    _created, manifest_path, clip_count = build_playlist(
        attempts,
        logs,
        config=_editorial_config(),
        inference_inputs_path=inputs,
        game="rushn_attack",
        mission="m1",
        editorial=True,
    )
    assert manifest_path and manifest_path.is_file()
    assert clip_count <= 2
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest.get("kind") == "editorial"
    assert all(c.get("slug") == "episode_reward" for c in manifest["clips"])
    air = measure_playlist_airtime(manifest_path)
    assert air.seconds <= 30.0 + 5.0  # допуск на hold/короткие клипы
