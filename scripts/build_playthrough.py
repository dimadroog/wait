#!/usr/bin/env python3
"""Сборка эталона: human_playthrough.jsonl, routes, manifest, save states, demos."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from mission_states import save_fm2_states  # noqa: E402
from phase0_config import load_phase0_config, transition_rooms_from_config  # noqa: E402
from playthrough_build import (  # noqa: E402
    build_playthrough_artifacts,
    gameplay_start_frame_from_rows,
    inference_save_state_plan,
    save_state_plan,
)
from project_paths import (  # noqa: E402
    count_fm2_frames,
    resolve_mission_fm2,
    resolve_ram_scout_jsonl,
    resolve_rom,
)
from ram_resolve import load_frames  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build playthrough etalon from FM2 + ram_scout logs")
    parser.add_argument(
        "fm2",
        help="путь к FM2: games/<game>/missions/<mission>/reference/<file>.fm2",
    )
    parser.add_argument("--timeout", type=float, default=600.0, help="секунд на FCEUX (save states)")
    parser.add_argument("--skip-states", action="store_true", help="не создавать save states")
    parser.add_argument(
        "--skip-inference-states",
        action="store_true",
        help="не создавать states/inference_cp0.fc0 (gameplay start)",
    )
    parser.add_argument("--skip-demos", action="store_true", help="не создавать demos/seg_*.npz")
    args = parser.parse_args()

    try:
        fm2, game_id, mission = resolve_mission_fm2(args.fm2)
    except (FileNotFoundError, ValueError) as e:
        raise SystemExit(str(e)) from e

    jsonl, _legacy = resolve_ram_scout_jsonl(mission)
    if not jsonl.is_file():
        raise SystemExit(
            f"ram_scout.jsonl not found: {jsonl}. Run ram_scout.py first."
        )

    frames = load_frames(jsonl)
    print(f"Frames: {len(frames)} from {jsonl}")

    phase0 = load_phase0_config(game_id)
    rows, segments = build_playthrough_artifacts(mission, game_id, fm2, frames, phase0)
    gameplay_frame = gameplay_start_frame_from_rows(
        rows, transition_rooms=transition_rooms_from_config(phase0)
    )
    print(f"Gameplay start frame: {gameplay_frame}")
    print("Wrote reference/human_playthrough.jsonl")
    print("Wrote config/routes.yaml, config/playthrough_manifest.yaml")

    timeout = max(args.timeout, count_fm2_frames(fm2) / 30.0 + 60.0)

    if not args.skip_states:
        rom = resolve_rom(game_id)
        plan = save_state_plan(segments)
        save_fm2_states(
            mission,
            fm2,
            rom,
            plan,
            timeout_sec=timeout,
            staging_subdir="save_states",
            tmp_subdir="save_states",
        )

    if not args.skip_inference_states and not args.skip_states:
        rom = resolve_rom(game_id)
        inf_plan = inference_save_state_plan(gameplay_frame)
        save_fm2_states(
            mission,
            fm2,
            rom,
            inf_plan,
            timeout_sec=timeout,
            staging_subdir="inference_states",
            tmp_subdir="inference_states",
        )

    if not args.skip_demos:
        from segment_playthrough import build_demos  # noqa: E402

        build_demos(mission)
        print("Wrote demos/seg_*.npz")

    print("Done.")


if __name__ == "__main__":
    main()
