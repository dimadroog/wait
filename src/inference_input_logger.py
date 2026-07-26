"""Покадровый лог inference → logs/<model_version>/inference_inputs.jsonl."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonl_logs import append_jsonl, gen_log_path


class InferenceInputLogger:
    def __init__(self, logs_dir: str | Path, *, model_version: str = "smoke") -> None:
        self.logs_dir = Path(logs_dir)
        self.model_version = model_version
        self._path = gen_log_path(self.logs_dir, model_version, "inference_inputs")
        self._episode = 0

    @property
    def log_path(self) -> Path:
        return self._path

    def begin_episode(self, episode: int) -> None:
        self._episode = episode

    def log_step(
        self,
        *,
        step: int,
        frame: int,
        action: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        record: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "episode": self._episode,
            "step": step,
            "frame": frame,
            "action": action or "",
        }
        if extra:
            record.update(extra)
        append_jsonl(self._path, record)
