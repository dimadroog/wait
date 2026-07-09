#!/usr/bin/env python3
"""Save states для inference: inference_cp0 на кадре gameplay start (не intro)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from inference_config import inference_save_state_for  # noqa: E402
from mission_states import save_fm2_states  # noqa: E402
from phase0_config import load_phase0_config, transition_rooms_from_config  # noqa: E402
from playthrough_build import (  # noqa: E402
    gameplay_start_frame_from_rows,
    inference_save_state_plan,
    load_human_playthrough_rows,
)
from project_paths import (  # noqa: E402
    count_fm2_frames,
    load_yaml,
    resolve_mission_fm2,
    resolve_rom,
)


def _update_manifest_inference(mission: Path, gameplay_frame: int) -> None:
    import yaml

    manifest_path = mission / "config" / "playthrough_manifest.yaml"
    if not manifest_path.is_file():
        raise SystemExit(f"Manifest not found: {manifest_path}. Run build_playthrough.py first.")
    doc = load_yaml(manifest_path)
    doc["inference"] = {
        "gameplay_start_frame": gameplay_frame,
        "save_state": inference_save_state_for(0),
    }
    manifest_path.write_text(
        yaml.dump(doc, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build inference save states (gameplay start, not FM2 frame 1)"
    )
    parser.add_argument(
        "fm2",
        nargs="?",
        default="games/rushn_attack/missions/m1/reference/clear.fm2",
        help="путь к FM2 в reference/",
    )
    parser.add_argument("--timeout", type=float, default=600.0, help="секунд на FCEUX")
    args = parser.parse_args()

    try:
        fm2, game_id, mission = resolve_mission_fm2(args.fm2)
    except (FileNotFoundError, ValueError) as e:
        raise SystemExit(str(e)) from e

    jsonl = mission / "reference" / "human_playthrough.jsonl"
    if not jsonl.is_file():
        raise SystemExit(f"{jsonl} not found. Run build_playthrough.py first.")

    rows = load_human_playthrough_rows(jsonl)
    phase0 = load_phase0_config(game_id)
    gameplay_frame = gameplay_start_frame_from_rows(
        rows, transition_rooms=transition_rooms_from_config(phase0)
    )
    plan = inference_save_state_plan(gameplay_frame)
    rom = resolve_rom(game_id)
    timeout = max(args.timeout, count_fm2_frames(fm2) / 30.0 + 60.0)

    print(f"Gameplay start: frame {gameplay_frame} (room outside intro)")
    print(f"FM2: {fm2}")
    save_fm2_states(
        mission,
        fm2,
        rom,
        plan,
        timeout_sec=timeout,
        staging_subdir="inference_states",
        tmp_subdir="inference_states",
    )
    _update_manifest_inference(mission, gameplay_frame)
    print(f"Wrote {inference_save_state_for(0)} and manifest inference block")
    print("Done.")


if __name__ == "__main__":
    main()
