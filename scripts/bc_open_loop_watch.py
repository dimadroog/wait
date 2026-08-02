#!/usr/bin/env python3
"""BC open-loop watch: FCEUX + greedy pred vs human (max gameplay match)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from bc_open_loop_eval import (  # noqa: E402
    FrameAction,
    build_open_loop_replay_frames,
    evaluate_open_loop,
    load_human_playthrough,
    parse_attack_window,
    resolve_mission_paths,
)
from env.loader import make_env  # noqa: E402
from project_paths import (  # noqa: E402
    add_game_mission_arguments,
    apply_resolved_game_mission,
)


def _log(msg: str) -> None:
    print(msg, flush=True)


def _resolve_model_zip(model_arg: Path) -> Path:
    raw = model_arg.resolve()
    if raw.is_file() and raw.suffix.lower() == ".zip":
        return raw
    zip_path = raw if raw.suffix.lower() == ".zip" else raw.with_suffix(".zip")
    if zip_path.is_file():
        return zip_path
    raise FileNotFoundError(f"model zip not found: {model_arg}")


def _load_model(game_id: str, model_path: Path) -> tuple[object, object | None]:
    from train.phase_aware_ppo import PhaseAwarePPO
    from train.phase_heads import load_policy_heads_spec

    heads_spec = load_policy_heads_spec(game_id)
    model = PhaseAwarePPO.load(str(model_path.with_suffix("")), device="cpu")
    model.heads_spec = heads_spec
    return model, heads_spec


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "BC open-loop watch: human trajectory in FCEUX, greedy pred vs human in console. "
            "Max gameplay action match (not closed-loop agent play)."
        )
    )
    add_game_mission_arguments(parser)
    parser.add_argument("--model", type=Path, required=True, help="path to BC .zip")
    parser.add_argument("--frame-start", type=int, default=1034)
    parser.add_argument("--frame-end", type=int, default=1300)
    parser.add_argument("--frame-skip", type=int, default=4, help="decision cadence")
    parser.add_argument("--attack-window", default="1195-1210")
    parser.add_argument(
        "--save-state",
        default="save_states/cp_gameplay0.fc0",
        help="reset save state",
    )
    parser.add_argument(
        "--no-window",
        action="store_true",
        help="headless (fast check, no FCEUX window)",
    )
    parser.add_argument(
        "--realtime",
        action="store_true",
        help="disable turbo (slow, for viewing every NES frame)",
    )
    args = parser.parse_args()

    game_id, mission_id = apply_resolved_game_mission(args)
    mission = resolve_mission_paths(game_id, mission_id)
    attack_window = parse_attack_window(args.attack_window)
    aw_start, aw_end = attack_window

    from train.env_factory import cleanup_bridge_sessions, kill_orphan_fceux_bridge
    from train.phase_heads import load_game_action_strings

    action_strings = load_game_action_strings(game_id)
    model_path = _resolve_model_zip(args.model)

    _log(f"loading model {model_path.name}...")
    model, heads_spec = _load_model(game_id, model_path)

    human_frames = load_human_playthrough(
        mission,
        frame_start=args.frame_start,
        frame_end=args.frame_end,
        frame_skip=args.frame_skip,
        action_strings=action_strings,
    )
    replay_frames = build_open_loop_replay_frames(
        mission,
        frame_end=args.frame_end,
        save_state=args.save_state,
        action_strings=action_strings,
    )
    if not human_frames:
        raise SystemExit("no human decision frames in range")

    show_window = not args.no_window
    turbo = not args.realtime

    def on_decision(
        decision: FrameAction,
        pred_action: str,
        human_action: str,
        matched: bool,
    ) -> None:
        mark = "OK" if matched else "MISS"
        tag = " attack" if aw_start <= decision.frame <= aw_end else ""
        _log(
            f"frame {decision.frame}{tag}: human={human_action!r} pred={pred_action!r} [{mark}]"
        )

    cleanup_bridge_sessions(prefix="bench_")
    kill_orphan_fceux_bridge()
    _log("starting FCEUX...")
    env = make_env(
        game_id,
        mission_id,
        session_id="bench_ol_0",
        save_state=args.save_state,
        turbo=turbo,
        show_window=show_window,
        frame_skip=1,
        obs_format="raw" if show_window else None,
    )
    try:
        if show_window:
            _log(
                "watch: human drives gameplay; lines below = BC greedy vs human "
                "(OK/MISS on decision frames)"
            )
        report = evaluate_open_loop(
            model,
            env,
            heads_spec,
            human_frames,
            action_strings,
            save_state=args.save_state,
            attack_window=attack_window,
            replay_frames=replay_frames,
            on_decision=on_decision,
        )
    finally:
        env.close()
        cleanup_bridge_sessions(prefix="bench_")

    _log(
        f"done: {report.stats.correct}/{report.stats.total} "
        f"({report.stats.pct:.1f}%), B={report.stats.b_pct:.1f}%, "
        f"move={report.stats.move_pct:.1f}%"
    )


if __name__ == "__main__":
    main()
