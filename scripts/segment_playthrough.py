#!/usr/bin/env python3
"""Нарезка reference/demos_for_bc/seg_*.npz из manifest + human_playthrough.jsonl."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import yaml

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from playthrough_build import encode_action  # noqa: E402
from project_paths import demos_for_bc_dir  # noqa: E402


def _load_human_jsonl(path: Path) -> dict[int, dict]:
    by_frame: dict[int, dict] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                row = json.loads(line)
                by_frame[row["frame"]] = row
    return by_frame


def build_demos(mission: Path) -> list[Path]:
    manifest_path = mission / "config" / "playthrough_manifest.yaml"
    human_path = mission / "reference" / "human_playthrough.jsonl"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"manifest not found: {manifest_path}")
    if not human_path.is_file():
        raise FileNotFoundError(f"human_playthrough.jsonl not found: {human_path}")

    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    by_frame = _load_human_jsonl(human_path)
    demos_dir = demos_for_bc_dir(mission)
    demos_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for seg in manifest.get("segments", []):
        start = int(seg["frame_start"])
        end = int(seg["frame_end"])
        actions: list[int] = []
        for frame in range(start, end + 1):
            row = by_frame.get(frame)
            if row is None:
                continue
            actions.append(encode_action(row.get("action", "")))
        n = len(actions)
        if n == 0:
            continue
        obs = np.zeros((n, 4, 84, 84), dtype=np.float32)
        act = np.array(actions, dtype=np.int64)
        segment_meta_json = json.dumps(
            {
                "segment_id": seg["id"],
                "mission": mission.name,
                "frame_start": start,
                "frame_end": end,
                "obs_stub": True,
            }
        )
        out = demos_dir / f"{seg['id']}.npz"
        np.savez_compressed(out, obs=obs, actions=act, meta=np.array(segment_meta_json))
        written.append(out)
    return written


def main() -> None:
    import argparse

    from project_paths import resolve_mission_fm2

    parser = argparse.ArgumentParser(description="Segment playthrough into reference/demos_for_bc/*.npz")
    parser.add_argument(
        "fm2",
        help="путь к FM2 (для определения миссии): games/.../reference/<file>.fm2",
    )
    args = parser.parse_args()
    try:
        _, _, mission = resolve_mission_fm2(args.fm2)
    except (FileNotFoundError, ValueError) as e:
        raise SystemExit(str(e)) from e
    paths = build_demos(mission)
    for p in paths:
        print(p)


if __name__ == "__main__":
    main()
