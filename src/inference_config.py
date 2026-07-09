"""Inference FM2 GUID и выбор save state для replay/export."""
from __future__ import annotations

from pathlib import Path

from project_paths import load_yaml

# Отдельный GUID от эталона (clear.fm2); стабильный для всех inference-movie.
INFERENCE_FM2_GUID = "B1AEF103-0001-4000-8000-000000000001"


def inference_fm2_guid() -> str:
    return INFERENCE_FM2_GUID


def inference_save_state_for(cp_index: int) -> str:
    return f"states/inference_cp{cp_index}.fc0"


def gameplay_start_frame(mission: Path) -> int | None:
    """Кадр старта gameplay из config/playthrough_manifest.yaml (inference block)."""
    manifest = mission / "config" / "playthrough_manifest.yaml"
    if not manifest.is_file():
        return None
    data = load_yaml(manifest)
    inference = data.get("inference") or {}
    frame = inference.get("gameplay_start_frame")
    return int(frame) if frame is not None else None


def resolve_inference_save_state(mission: Path, *, cp_index: int = 0) -> str:
    """Путь относительно mission; inference_cpN, иначе cpN (legacy train states)."""
    manifest = mission / "config" / "playthrough_manifest.yaml"
    if manifest.is_file() and cp_index == 0:
        data = load_yaml(manifest)
        inference = data.get("inference") or {}
        rel = inference.get("save_state")
        if rel and (mission / rel).is_file():
            return str(rel)

    inf = mission / inference_save_state_for(cp_index)
    if inf.is_file():
        return inference_save_state_for(cp_index)
    return f"states/cp{cp_index}.fc0"
