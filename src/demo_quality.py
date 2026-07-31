"""Контроль качества BC-демо (seg_*.npz): отсев чёрных / shell-кадров."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from obs_contract import OBS_SHAPE, validate_obs_stack

DEFAULT_BLACK_MEAN = 0.08
DEFAULT_MIN_OBS_STD = 0.05
DEFAULT_MAX_BLACK_FRACTION = 0.5
DEFAULT_MIN_GAMEPLAY_FRACTION = 0.7


@dataclass(frozen=True)
class DemoQualityMetrics:
    n_steps: int
    black_fraction: float
    obs_std: float
    gameplay_fraction: float
    obs_max: float

    @property
    def passed(self) -> bool:
        return not self.failure_reasons()

    def failure_reasons(self) -> list[str]:
        reasons: list[str] = []
        if self.black_fraction >= DEFAULT_MAX_BLACK_FRACTION:
            reasons.append(
                f"black_fraction={self.black_fraction:.3f} >= {DEFAULT_MAX_BLACK_FRACTION}"
            )
        if self.obs_std < DEFAULT_MIN_OBS_STD:
            reasons.append(f"obs_std={self.obs_std:.4f} < {DEFAULT_MIN_OBS_STD}")
        return reasons

    def reasons_ok(self) -> list[str]:
        """Список причин провала метрик (alias failure_reasons)."""
        return self.failure_reasons()


@dataclass(frozen=True)
class SegmentQualityResult:
    segment_id: str
    metrics: DemoQualityMetrics
    require_gameplay: bool

    @property
    def passed(self) -> bool:
        if not self.metrics.passed:
            return False
        if self.require_gameplay and self.metrics.gameplay_fraction < DEFAULT_MIN_GAMEPLAY_FRACTION:
            return False
        return True

    def failure_reasons(self) -> list[str]:
        reasons = list(self.metrics.reasons_ok())
        if (
            self.require_gameplay
            and self.metrics.gameplay_fraction < DEFAULT_MIN_GAMEPLAY_FRACTION
        ):
            reasons.append(
                f"gameplay_fraction={self.metrics.gameplay_fraction:.3f} "
                f"< {DEFAULT_MIN_GAMEPLAY_FRACTION}"
            )
        return reasons


def _last_plane(obs_step: np.ndarray) -> np.ndarray:
    plane = np.asarray(obs_step, dtype=np.float32)
    if plane.ndim == 3:
        return plane[-1]
    return plane


def is_black_frame(plane: np.ndarray, *, threshold: float = DEFAULT_BLACK_MEAN) -> bool:
    return float(np.mean(plane)) < threshold


def is_gameplay_like_frame(plane: np.ndarray, *, threshold: float = DEFAULT_BLACK_MEAN) -> bool:
    """Геймплей: не почти чёрный кадр и есть контраст (не однородная заливка)."""
    if is_black_frame(plane, threshold=threshold):
        return False
    return float(np.std(plane)) > 0.02


def compute_metrics(obs: np.ndarray) -> DemoQualityMetrics:
    """Метрики по массиву obs (N, 4, H, W) float32."""
    n = int(obs.shape[0])
    if n == 0:
        return DemoQualityMetrics(0, 1.0, 0.0, 0.0, 0.0)

    black = 0
    gameplay = 0
    for i in range(n):
        plane = _last_plane(obs[i])
        if is_black_frame(plane):
            black += 1
        if is_gameplay_like_frame(plane):
            gameplay += 1

    flat = obs.astype(np.float32).ravel()
    return DemoQualityMetrics(
        n_steps=n,
        black_fraction=black / n,
        obs_std=float(np.std(flat)),
        gameplay_fraction=gameplay / n,
        obs_max=float(np.max(obs)),
    )


def parse_demo_meta(npz: np.lib.npyio.NpzFile) -> dict[str, Any]:
    raw = npz["meta"]
    text = raw.item() if hasattr(raw, "item") else raw
    meta = json.loads(str(text))
    if not isinstance(meta, dict):
        raise ValueError("demo meta must be a JSON object")
    return meta


def evaluate_segment_quality(
    obs: np.ndarray,
    *,
    segment_id: str,
    frame_start: int,
    gameplay_start_frame: int | None,
) -> SegmentQualityResult:
    require_gameplay = (
        gameplay_start_frame is not None and int(frame_start) >= int(gameplay_start_frame)
    )
    return SegmentQualityResult(
        segment_id=segment_id,
        metrics=compute_metrics(obs),
        require_gameplay=require_gameplay,
    )


def validate_demo_npz(
    path: Path,
    *,
    gameplay_start_frame: int | None = None,
) -> SegmentQualityResult:
    with np.load(path, allow_pickle=True) as z:
        meta = parse_demo_meta(z)
        obs = np.asarray(z["obs"], dtype=np.float32)
    validate_obs_stack(obs)
    seg_id = str(meta.get("segment_id") or path.stem)
    frame_start = int(meta.get("frame_start", 0))
    if gameplay_start_frame is None and meta.get("gameplay_start_frame") is not None:
        gameplay_start_frame = int(meta["gameplay_start_frame"])
    return evaluate_segment_quality(
        obs,
        segment_id=seg_id,
        frame_start=frame_start,
        gameplay_start_frame=gameplay_start_frame,
    )


def validate_all_demos(
    paths: list[Path],
    *,
    gameplay_start_frame: int | None = None,
) -> list[SegmentQualityResult]:
    return [validate_demo_npz(p, gameplay_start_frame=gameplay_start_frame) for p in paths]
