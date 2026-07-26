"""Inference reset save state (= канон gameplay, тот же что train)."""
from __future__ import annotations

from pathlib import Path

from playthrough_build import default_gameplay_save_rel, load_head_save_states
from project_paths import load_yaml


def gameplay_start_frame(mission: Path) -> int | None:
    """Кадр старта gameplay из manifest (train/inference / head_save_states)."""
    manifest = mission / "config" / "playthrough_manifest.yaml"
    if not manifest.is_file():
        return None
    manifest_yaml = load_yaml(manifest)
    for key in ("inference", "train"):
        block = manifest_yaml.get(key) or {}
        frame = block.get("gameplay_start_frame")
        if frame is not None:
            return int(frame)
    heads = load_head_save_states(mission)
    if heads and heads.get("gameplay"):
        return int(heads["gameplay"][0]["frame"])
    return None


def resolve_inference_reset_state(mission: Path) -> str:
    """Путь относительно mission для inference env reset и FM2 embed."""
    manifest = mission / "config" / "playthrough_manifest.yaml"
    if manifest.is_file():
        manifest_yaml = load_yaml(manifest)
        for key in ("inference", "train"):
            block = manifest_yaml.get(key) or {}
            rel = block.get("save_state")
            if rel and (mission / str(rel)).is_file():
                return str(rel)
        heads = load_head_save_states(mission)
        rel = default_gameplay_save_rel(heads)
        if (mission / rel).is_file():
            return rel
        raise FileNotFoundError(
            f"Inference/train save state not found (tried manifest + {rel}). "
            "Run: scripts/build_playthrough.py … --states-only"
        )

    rel = default_gameplay_save_rel(None)
    path = mission / rel
    if path.is_file():
        return rel
    raise FileNotFoundError(
        f"Inference save state not found: {path}. "
        "Run: scripts/build_playthrough.py … --states-only"
    )
