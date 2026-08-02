#!/usr/bin/env python3
"""BC open-loop / closed-loop диагностика: argv → bc_open_loop_eval."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from bc_open_loop_eval import (  # noqa: E402
    FrameAction,
    build_open_loop_replay_frames,
    build_transfer_verdict,
    default_human_playthrough_path,
    evaluate_closed_loop_from_logs,
    evaluate_npz_offline,
    evaluate_open_loop,
    load_human_playthrough,
    parse_attack_window,
    resolve_mission_paths,
    write_reports,
)
from env.loader import make_env  # noqa: E402
from project_paths import (  # noqa: E402
    add_game_mission_arguments,
    apply_resolved_game_mission,
)


def _resolve_model_zip(model_arg: Path) -> Path:
    raw = model_arg.resolve()
    if raw.is_file() and raw.suffix.lower() == ".zip":
        return raw
    if raw.is_dir():
        candidate = raw.with_suffix(".zip")
        if candidate.is_file():
            return candidate
        raise FileNotFoundError(f"model zip not found next to directory: {raw}")
    zip_path = raw if raw.suffix.lower() == ".zip" else raw.with_suffix(".zip")
    if zip_path.is_file():
        return zip_path
    raise FileNotFoundError(f"model zip not found: {model_arg}")


def _load_model(game_id: str, model_path: Path) -> tuple[object, object | None]:
    from stable_baselines3 import PPO
    from train.phase_aware_ppo import PhaseAwarePPO
    from train.phase_heads import load_policy_heads_spec

    heads_spec = load_policy_heads_spec(game_id)
    load_stem = str(model_path.with_suffix(""))
    if heads_spec is None:
        return PPO.load(load_stem, device="cpu"), None
    model = PhaseAwarePPO.load(load_stem, device="cpu")
    if not hasattr(model.policy, "set_active_head"):
        raise SystemExit("policy_heads set but model has no set_active_head")
    model.heads_spec = heads_spec
    return model, heads_spec


def _make_open_loop_env(
    game_id: str,
    mission_id: str,
    *,
    save_state: str,
    show_window: bool = False,
    turbo: bool = True,
) -> object:
    session_id = "bench_ol_0"
    return make_env(
        game_id,
        mission_id,
        session_id=session_id,
        save_state=save_state,
        turbo=turbo,
        show_window=show_window,
        frame_skip=1,
        # BC train/inference obs = raw grayscale из lua; gd+opencv даёт другой pipeline.
        obs_format="raw" if show_window else None,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "BC transfer diagnostic: open-loop greedy match on human trajectory "
            "+ optional closed-loop compare from inference_inputs.jsonl"
        )
    )
    add_game_mission_arguments(parser)
    parser.add_argument(
        "--model",
        type=Path,
        default=None,
        help="path to model .zip (required unless --no-fceux)",
    )
    parser.add_argument("--frame-start", type=int, default=1034)
    parser.add_argument("--frame-end", type=int, default=1300)
    parser.add_argument("--frame-skip", type=int, default=4)
    parser.add_argument("--attack-window", default="1195-1210")
    parser.add_argument(
        "--closed-loop-logs",
        type=Path,
        default=None,
        help="inference_inputs.jsonl from closed-loop run",
    )
    parser.add_argument(
        "--human-path",
        type=Path,
        default=None,
        help="override human_playthrough.jsonl",
    )
    parser.add_argument(
        "--save-state",
        default="save_states/cp_gameplay0.fc0",
        help="env reset save state for open-loop",
    )
    parser.add_argument("--segment", default="seg_002", help="NPZ segment for offline baseline")
    parser.add_argument("--out", type=Path, default=Path("tmp/bench/bc_open_loop"))
    parser.add_argument(
        "--no-fceux",
        action="store_true",
        help="skip open-loop (FCEUX); only closed-loop from logs",
    )
    parser.add_argument("--run-label", default="", help="label in verdict markdown")
    parser.add_argument("--episode", type=int, default=1, help="episode in inference log")
    parser.add_argument(
        "--watch",
        action="store_true",
        help="окно FCEUX: human-траектория + pred vs human в консоли (open-loop)",
    )
    parser.add_argument(
        "--turbo",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--realtime",
        action="store_true",
        help="disable turbo (slow FCEUX; for --watch)",
    )
    args = parser.parse_args()

    game_id, mission_id = apply_resolved_game_mission(args)
    mission = resolve_mission_paths(game_id, mission_id)
    attack_window = parse_attack_window(args.attack_window)
    human_path = args.human_path or default_human_playthrough_path(mission)

    from train.phase_heads import load_game_action_strings

    action_strings = load_game_action_strings(game_id)

    open_report = None
    npz_report = None
    model_path_str = ""
    model = None
    heads_spec = None

    if args.model is not None:
        model_zip = _resolve_model_zip(args.model)
        model_path_str = str(model_zip)
        if args.watch:
            print(f"loading model {model_zip.name}...", flush=True)
        model, heads_spec = _load_model(game_id, model_zip)
        if not args.watch:
            npz_report = evaluate_npz_offline(
                model,
                mission,
                heads_spec,
                action_strings,
                segment_id=args.segment,
            )
            print(
                f"npz offline ({args.segment}): {npz_report.stats.correct}/{npz_report.stats.total} "
                f"({npz_report.stats.pct:.1f}%), B={npz_report.stats.b_pct:.1f}%",
                flush=True,
            )

    if not args.no_fceux:
        if model is None:
            raise SystemExit("--model is required unless --no-fceux")
        from train.env_factory import cleanup_bridge_sessions

        cleanup_bridge_sessions(prefix="bench_")
        human_frames = load_human_playthrough(
            mission,
            frame_start=args.frame_start,
            frame_end=args.frame_end,
            frame_skip=args.frame_skip,
            action_strings=action_strings,
            human_path=human_path,
        )
        replay_frames = build_open_loop_replay_frames(
            mission,
            frame_end=args.frame_end,
            save_state=args.save_state,
            action_strings=action_strings,
            human_path=human_path,
        )
        if not human_frames:
            raise SystemExit("no human decision frames in range")

        show_window = bool(args.watch)
        turbo = not args.realtime
        on_decision = None
        if show_window:
            aw_start, aw_end = attack_window

            def on_decision(
                decision: FrameAction,
                pred_action: str,
                human_action: str,
                matched: bool,
            ) -> None:
                mark = "OK" if matched else "MISS"
                in_aw = aw_start <= decision.frame <= aw_end
                tag = " attack" if in_aw else ""
                print(
                    f"frame {decision.frame}{tag}: human={human_action!r} pred={pred_action!r} [{mark}]"
                )

        env = _make_open_loop_env(
            game_id,
            mission_id,
            save_state=args.save_state,
            show_window=show_window,
            turbo=turbo,
        )
        try:
            if show_window:
                print(
                    "watch: FCEUX open-loop - human trajectory on screen, "
                    "console shows model pred vs human (OK/MISS)"
                )
                print("Starting FCEUX window...")
            open_report = evaluate_open_loop(
                model,
                env,
                heads_spec,
                human_frames,
                action_strings,
                save_state=args.save_state,
                attack_window=attack_window,
                human_path=human_path,
                replay_frames=replay_frames,
                on_decision=on_decision,
            )
            print(
                f"open-loop: {open_report.stats.correct}/{open_report.stats.total} "
                f"({open_report.stats.pct:.1f}%), B={open_report.stats.b_pct:.1f}%"
            )
        finally:
            env.close()
            cleanup_bridge_sessions(prefix="bench_")

    closed_report = None
    inference_path_str = ""
    if args.closed_loop_logs is not None:
        inference_path_str = str(args.closed_loop_logs)
        closed_report = evaluate_closed_loop_from_logs(
            args.closed_loop_logs,
            human_path,
            action_strings,
            frame_start=args.frame_start,
            frame_end=args.frame_end,
            frame_skip=args.frame_skip,
            attack_window=attack_window,
            episode=args.episode,
        )
        print(
            f"closed-loop (ep {closed_report.episode}): "
            f"{closed_report.stats.correct}/{closed_report.stats.total} "
            f"({closed_report.stats.pct:.1f}%), "
            f"attack B={closed_report.stats.attack_window_b_pct:.1f}%"
        )

    verdict = build_transfer_verdict(open_report, closed_report, npz_offline=npz_report)
    print(f"verdict: {verdict.label} — {verdict.details}")

    paths = write_reports(
        args.out.resolve(),
        open_loop=open_report,
        closed_loop=closed_report,
        npz_offline=npz_report,
        verdict=verdict,
        model_path=model_path_str,
        inference_path=inference_path_str,
        run_label=args.run_label,
    )
    for name, path in paths.items():
        print(f"wrote {name}: {path}")


if __name__ == "__main__":
    main()
