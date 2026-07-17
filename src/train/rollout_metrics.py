"""Метрики wall/rollout (+ опц. RAM) для dual train + fps-диагностика."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from stable_baselines3.common.callbacks import BaseCallback


def host_memory_mb() -> dict[str, float | None]:
    """Свободная/доступная RAM хоста (Windows MEMORYSTATUSEX; иначе None)."""
    try:
        import ctypes
        from ctypes import wintypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", wintypes.DWORD),
                ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_uint64),
                ("ullAvailPhys", ctypes.c_uint64),
                ("ullTotalPageFile", ctypes.c_uint64),
                ("ullAvailPageFile", ctypes.c_uint64),
                ("ullTotalVirtual", ctypes.c_uint64),
                ("ullAvailVirtual", ctypes.c_uint64),
                ("ullAvailExtendedVirtual", ctypes.c_uint64),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return {"avail_phys_mb": None, "total_phys_mb": None, "memory_load_pct": None}
        return {
            "avail_phys_mb": round(stat.ullAvailPhys / (1024 * 1024), 1),
            "total_phys_mb": round(stat.ullTotalPhys / (1024 * 1024), 1),
            "memory_load_pct": float(stat.dwMemoryLoad),
        }
    except Exception:
        return {"avail_phys_mb": None, "total_phys_mb": None, "memory_load_pct": None}


class RolloutMetricsCallback(BaseCallback):
    """Пишет одну JSONL-строку на rollout: wall_s, timesteps, RAM snapshot."""

    def __init__(self, jsonl_path: Path, verbose: int = 0):
        super().__init__(verbose)
        self._path = Path(jsonl_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._rollout_idx = 0
        self._t0 = time.perf_counter()
        self._prev_t = self._t0
        self._prev_steps = 0

    def _on_training_start(self) -> None:
        self._t0 = time.perf_counter()
        self._prev_t = self._t0
        self._prev_steps = int(self.model.num_timesteps)
        self._rollout_idx = 0

    def _on_step(self) -> bool:
        return True

    def _on_rollout_end(self) -> bool:
        self._rollout_idx += 1
        now = time.perf_counter()
        steps = int(self.model.num_timesteps)
        wall_s = now - self._prev_t
        delta_steps = max(steps - self._prev_steps, 0)
        row: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "rollout": self._rollout_idx,
            "num_timesteps": steps,
            "delta_timesteps": delta_steps,
            "wall_rollout_s": round(wall_s, 3),
            "env_steps_per_s": round(delta_steps / wall_s, 3) if wall_s > 0 else None,
            "elapsed_s": round(now - self._t0, 3),
            **host_memory_mb(),
        }
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        if self.verbose:
            print(
                f"rollout_metrics: #{self._rollout_idx} wall={wall_s:.1f}s "
                f"steps={delta_steps} rate={row['env_steps_per_s']} "
                f"avail_ram_mb={row.get('avail_phys_mb')}"
            )
        self._prev_t = now
        self._prev_steps = steps
        return True
