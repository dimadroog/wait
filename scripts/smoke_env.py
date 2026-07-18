"""Smoke test: random agent, 100 steps, game env + rewards."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from attempt_logger import AttemptLogger  # noqa: E402
from env import make_env  # noqa: E402
from project_paths import mission_dir  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test game env (random agent)")
    parser.add_argument("--game", default="rushn_attack")
    parser.add_argument("--mission", default="m1")
    parser.add_argument("--steps", type=int, default=100)
    parser.add_argument("--save-state", default=None, help="save_states/cpN.fc0 относительно миссии")
    parser.add_argument("--session", default="smoke_env", help="FCEUX bridge session id")
    parser.add_argument(
        "--death-mode",
        default=None,
        choices=["life_lost", "game_over"],
        help="override env_config death_mode (H3)",
    )
    parser.add_argument("--log", action="store_true", help="append logs/attempts.jsonl")
    args = parser.parse_args()

    mission = mission_dir(args.game, args.mission)
    state = mission / "save_states" / "cp1.fc0"
    if not state.is_file():
        state = mission / "save_states" / "cp0.fc0"
    if not state.is_file():
        raise SystemExit(f"Missing {state}. Run build_playthrough.py first.")

    kwargs: dict = {"session_id": args.session, "save_state": args.save_state or "save_states/cp1.fc0"}
    if args.death_mode:
        kwargs["death_mode"] = args.death_mode

    env = make_env(
        args.game,
        args.mission,
        wrap_rewards=True,
        **kwargs,
    )
    logger = AttemptLogger(mission / "logs") if args.log else None

    try:
        obs, info = env.reset()
        print(f"obs={obs.shape} dtype={obs.dtype} range=[{obs.min():.2f},{obs.max():.2f}]")
        print(f"reset ram: room={info['ram'].get('room')} x={info['ram'].get('x')} y={info['ram'].get('y')}")

        total_reward = 0.0
        last_info = info
        deaths = 0
        for step in range(1, args.steps + 1):
            action = env.action_space.sample()
            obs, reward, terminated, truncated, info = env.step(action)
            total_reward += reward
            last_info = info
            if info.get("died"):
                deaths += 1
                print(
                    f"death #{deaths} at step {step}: lives={info['ram'].get('lives')} "
                    f"terminated={terminated} death_mode={info.get('death_mode')}"
                )
            if step <= 3 or step == args.steps:
                print(
                    f"step {step}: a={action} r={reward:.3f} "
                    f"max_cp={info.get('max_checkpoint')} "
                    f"room={info['ram'].get('room')} x={info['ram'].get('x')}"
                )
            if terminated or truncated:
                print(
                    f"done at step {step}: terminated={terminated} truncated={truncated} "
                    f"deaths={deaths} ep_len={step}"
                )
                break

        print(
            f"OK steps={step} total_reward={total_reward:.3f} "
            f"max_cp={last_info.get('max_checkpoint')} deaths={deaths}"
        )
        if logger:
            logger.log_episode(mission=args.mission.replace("m", ""), episode=1, info=last_info)
            print(f"logged {mission / 'logs'}")
    finally:
        env.close()


if __name__ == "__main__":
    main()
