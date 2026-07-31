"""Платформенный контракт наблюдений для train / BC / inference."""
from __future__ import annotations

import numpy as np

FRAME_STACK = 4
OBS_WIDTH = 112
OBS_HEIGHT = 112
OBS_SHAPE = (FRAME_STACK, OBS_WIDTH, OBS_HEIGHT)
OBS_RAW_BYTES = OBS_WIDTH * OBS_HEIGHT


def obs_frame_shape() -> tuple[int, int]:
    return OBS_HEIGHT, OBS_WIDTH


def validate_obs_stack(arr: np.ndarray) -> None:
    """Проверить форму одного obs (4, H, W) или батча (N, 4, H, W)."""
    if arr.ndim == 3:
        if tuple(arr.shape) != OBS_SHAPE:
            raise ValueError(f"expected obs shape {OBS_SHAPE}, got {tuple(arr.shape)}")
        return
    if arr.ndim == 4:
        if tuple(arr.shape[1:]) != OBS_SHAPE:
            raise ValueError(
                f"expected obs shape (*, {OBS_SHAPE[0]}, {OBS_SHAPE[1]}, {OBS_SHAPE[2]}), "
                f"got {tuple(arr.shape)}"
            )
        return
    raise ValueError(f"obs must be 3D or 4D, got ndim={arr.ndim}")
