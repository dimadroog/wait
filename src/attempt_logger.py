"""Лог inference-попыток → logs/YYYYMMDD/attempts.jsonl (ML_CONCEPT §8)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonl_logs import append_jsonl, dated_log_path


class AttemptLogger:
    def __init__(self, logs_dir: str | Path) -> None:
        self.logs_dir = Path(logs_dir)
        self.log_path = dated_log_path(self.logs_dir, "attempts")

    def log_episode(
        self,
        *,
        mission: str | int,
        episode: int,
        info: dict[str, Any],
        model_version: str = "smoke",
        save_state: str | None = None,
        tags: list[str] | None = None,
        inference_inputs_ref: str | None = None,
    ) -> dict[str, Any]:
        ram = info.get("ram") or {}
        episode_frames = int(info.get("episode_frames", 0))
        episode_reward = float(info.get("episode_reward", 0.0))
        death_x = ram.get("x")
        record: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "model_version": model_version,
            "mission": mission,
            "episode": episode,
            "max_checkpoint": info.get("max_checkpoint", -1),
            "final_checkpoint": info.get("max_checkpoint", -1),
            "achieved_checkpoints": list(info.get("achieved_checkpoints") or []),
            "died": bool(info.get("died")),
            "death_x": death_x,
            "death_y": ram.get("y"),
            "death_room": ram.get("room"),
            "death_x_bucket": (int(death_x) // 16) if death_x is not None else None,
            "death_hp": ram.get("hp") if info.get("died") else None,
            "death_lives": ram.get("lives") if info.get("died") else None,
            "mission_clear": bool(info.get("mission_complete")),
            "episode_frames": episode_frames,
            "episode_reward": round(episode_reward, 3),
            "reward_per_step": round(episode_reward / episode_frames, 5) if episode_frames else 0.0,
            "save_state": save_state,
            "tags": list(tags or []),
        }
        if inference_inputs_ref:
            record["inference_inputs_ref"] = inference_inputs_ref
        append_jsonl(self.log_path, record)
        return record
