"""Inference reset save state (gameplay start); не train cp0."""
from __future__ import annotations

from pathlib import Path

from project_paths import load_yaml


def inference_save_state_for(cp_index: int) -> str:
    return f"states/inference_cp{cp_index}.fc0"


def gameplay_start_frame(mission: Path) -> int | None:
    """Кадр старта gameplay из config/playthrough_manifest.yaml (inference block)."""
    manifest = mission / "config" / "playthrough_manifest.yaml"
    if not manifest.is_file():
        return None
    manifest_yaml = load_yaml(manifest)
    inference = manifest_yaml.get("inference") or {}
    frame = inference.get("gameplay_start_frame")
    return int(frame) if frame is not None else None


def resolve_inference_reset_state(mission: Path, *, cp_index: int = 0) -> str:
    """Путь относительно mission для inference env reset и FM2 embed."""
    manifest = mission / "config" / "playthrough_manifest.yaml"
    if manifest.is_file() and cp_index == 0:
        manifest_yaml = load_yaml(manifest)
        inference = manifest_yaml.get("inference") or {}
        rel = inference.get("save_state")
        if rel:
            path = mission / rel
            if path.is_file():
                return str(rel)
            raise FileNotFoundError(f"Inference save state from manifest not found: {path}")

    rel = inference_save_state_for(cp_index)
    path = mission / rel
    if path.is_file():
        return rel
    raise FileNotFoundError(
        f"Inference save state not found: {path}. Run scripts/build_inference_states.py"
    )
