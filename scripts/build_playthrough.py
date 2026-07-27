#!/usr/bin/env python3
"""Сборка эталона: human_playthrough.jsonl, routes, manifest, save states, demos."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from mission_states import save_fm2_states  # noqa: E402
from etalon_build_config import (  # noqa: E402
    gameplay_start_rule_from_etalon_build,
    load_etalon_build_config,
    transition_rooms_from_etalon_build,
)
from playthrough_build import (  # noqa: E402
    build_playthrough_artifacts,
    gameplay_start_frame_from_head_saves,
    gameplay_start_frame_from_rows,
    load_head_save_states,
    save_state_plan,
)
from project_paths import (  # noqa: E402
    add_game_mission_arguments,
    clear_save_state_files,
    count_fm2_frames,
    resolve_cli_mission_fm2,
    ram_scout_jsonl_path,
    resolve_rom,
    save_states_dir,
)
from ram_resolve import load_frames  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build playthrough etalon from FM2 + ram_scout logs")
    parser.add_argument(
        "fm2",
        nargs="?",
        default=None,
        help=(
            "путь к FM2 от корня репо: games/<game>/missions/<mission>/reference/<file>.fm2; "
            "если опущен — clear.fm2 из workspace"
        ),
    )
    add_game_mission_arguments(parser)
    parser.add_argument("--timeout", type=float, default=600.0, help="секунд на FCEUX (save states)")
    parser.add_argument("--skip-states", action="store_true", help="не создавать save states")
    parser.add_argument("--skip-demos", action="store_true", help="не создавать reference/demos_for_bc/seg_*.npz")
    parser.add_argument(
        "--states-only",
        action="store_true",
        help="только пересобрать save_states из head_save_states (без routes/jsonl)",
    )
    parser.add_argument(
        "--replace-states",
        action="store_true",
        help="удалить все save_states/*.fc0 перед записью (иначе только слоты плана)",
    )
    parser.add_argument(
        "--force-demos",
        action="store_true",
        help="разрешить stub demos поверх non-stub (record_demos)",
    )
    args = parser.parse_args()

    try:
        fm2, game_id, mission = resolve_cli_mission_fm2(
            args.fm2, game=args.game, mission=args.mission
        )
    except (FileNotFoundError, ValueError) as e:
        raise SystemExit(str(e)) from e

    head_saves = load_head_save_states(mission)
    timeout = max(args.timeout, count_fm2_frames(fm2) / 30.0 + 60.0)

    if args.states_only:
        if not head_saves:
            raise SystemExit(
                "head_save_states missing in playthrough_manifest.yaml — "
                "нужны ручные якоря для --states-only"
            )
        plan = save_state_plan([], head_save_states=head_saves)
        gp = gameplay_start_frame_from_head_saves(head_saves)
        print(f"Gameplay start frame (head_save_states): {gp}")
        print(f"Saving {len(plan)} head save state(s)...")
        states = save_states_dir(mission)
        for old in clear_save_state_files(
            states, plan, replace_all=bool(args.replace_states)
        ):
            print(f"  removed {old.name}")
        rom = resolve_rom(game_id)
        save_fm2_states(
            mission,
            fm2,
            rom,
            plan,
            timeout_sec=timeout,
            staging_subdir="save_states",
            tmp_subdir="save_states",
        )
        print("Done.")
        return

    etalon_build = load_etalon_build_config(game_id)
    jsonl = ram_scout_jsonl_path(mission)
    if not jsonl.is_file():
        raise SystemExit(
            f"ram_scout.jsonl not found: {jsonl}. Run ram_scout.py first."
        )

    frames = load_frames(jsonl)
    print(f"Frames: {len(frames)} from {jsonl}")
    if etalon_build is None:
        print("No etalon_build.yaml — keep routes.yaml; anchors from head_save_states")

    rows, segments = build_playthrough_artifacts(mission, game_id, fm2, frames, etalon_build)
    head_saves = load_head_save_states(mission)
    gameplay_frame = gameplay_start_frame_from_head_saves(head_saves)
    if gameplay_frame is None:
        if etalon_build is None:
            raise SystemExit(
                "gameplay start: нужны head_save_states или games/<id>/etalon_build.yaml"
            )
        gameplay_frame = gameplay_start_frame_from_rows(
            rows,
            transition_rooms=transition_rooms_from_etalon_build(etalon_build),
            rule=gameplay_start_rule_from_etalon_build(etalon_build),
        )
    print(f"Gameplay start frame: {gameplay_frame}")
    print("Wrote reference/human_playthrough.jsonl")
    if etalon_build is not None:
        print("Wrote config/routes.yaml, config/playthrough_manifest.yaml")
    else:
        print("Wrote config/playthrough_manifest.yaml (routes.yaml unchanged)")

    if not args.skip_states:
        rom = resolve_rom(game_id)
        plan = save_state_plan(segments, gameplay_start_frame=gameplay_frame, head_save_states=head_saves)
        states = save_states_dir(mission)
        for old in clear_save_state_files(
            states, plan, replace_all=bool(args.replace_states)
        ):
            print(f"  removed {old.name}")
        save_fm2_states(
            mission,
            fm2,
            rom,
            plan,
            timeout_sec=timeout,
            staging_subdir="save_states",
            tmp_subdir="save_states",
        )

    if not args.skip_demos:
        from playthrough_build import build_demos  # noqa: E402

        build_demos(mission, force=bool(args.force_demos))
        print("Wrote reference/demos_for_bc/seg_*.npz")

    print("Done.")


if __name__ == "__main__":
    main()
