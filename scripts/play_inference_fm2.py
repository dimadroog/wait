#!/usr/bin/env python3
"""Проигрывание inference playlist / episode (emulation + jsonl, BACKLOG 3.4)."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from inference_replay import replay_frame_count, run_inference_playback  # noqa: E402
from inference_states import gameplay_start_frame  # noqa: E402
from project_paths import mission_dir, repo_root  # noqa: E402
from ram_map_load import load_ram_addresses  # noqa: E402


def _overlay_hold_frames(overlay_path: Path, default: int = 180) -> int:
    if not overlay_path.is_file():
        return default
    try:
        return int(json.loads(overlay_path.read_text(encoding="utf-8")).get("show_until_frame", default))
    except (json.JSONDecodeError, TypeError, ValueError):
        return default


def _resolve_input_path(path: Path, game: str, mission: str) -> Path:
    if path.is_absolute():
        return path.resolve()
    candidate = mission_dir(game, mission) / path
    return candidate.resolve() if candidate.is_file() else path.resolve()


def _playback_ram_env(game: str, mission: str, env: dict[str, str]) -> None:
    mdir = mission_dir(game, mission)
    try:
        addrs = load_ram_addresses(mdir)
        env["WAIT_PLAYBACK_ROOM"] = str(addrs["room"])
        if "lives" in addrs:
            env["WAIT_PLAYBACK_LIVES"] = str(addrs["lives"])
    except (FileNotFoundError, KeyError):
        pass
    gf = gameplay_start_frame(mdir)
    if gf is not None:
        env["WAIT_PLAYBACK_GAMEPLAY_START"] = str(gf)


def _play_episode(
    args: argparse.Namespace,
    *,
    jsonl_path: Path,
    episode: int,
    overlay_path: Path | None,
    block_label: str | None = None,
) -> None:
    staging = repo_root() / "tmp" / "play_inference" / f"ep{episode:04d}"
    tmp = staging / "tmp"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    env = os.environ.copy()
    if overlay_path and overlay_path.is_file():
        env["WAIT_ACHIEVEMENT_OVERLAY"] = str(overlay_path.resolve())
    if block_label:
        env["WAIT_BLOCK_LABEL"] = block_label
    _playback_ram_env(args.game, args.mission, env)

    frames = replay_frame_count(jsonl_path, episode)
    hold = _overlay_hold_frames(overlay_path) if overlay_path else 180
    timeout = max(args.timeout, (frames + hold) / 30.0 + 15.0)

    print(
        f"Playing episode {episode} from {jsonl_path.name} ({frames} frames)",
        flush=True,
    )
    if overlay_path and overlay_path.is_file():
        print(f"Overlay: {overlay_path}")

    run_inference_playback(
        jsonl_path=jsonl_path,
        episode=episode,
        staging=staging,
        tmp_dir=tmp,
        overlay_path=overlay_path,
        timeout_sec=timeout,
        turbo=args.turbo,
        game=args.game,
        mission=args.mission,
        extra_env=env,
    )


def _play_playlist(args: argparse.Namespace, playlist_path: Path) -> None:
    logs_dir = playlist_path.parent
    playlist = json.loads(playlist_path.read_text(encoding="utf-8"))
    clips = playlist.get("clips") or []
    if not clips:
        raise SystemExit(f"Playlist has no clips: {playlist_path}")

    print(f"Playlist {playlist_path.name}: {len(clips)} clip(s)", flush=True)
    for clip_idx, clip in enumerate(clips, start=1):
        inputs_name = clip.get("inference_inputs")
        if not inputs_name:
            raise SystemExit(f"Clip missing inference_inputs: {clip}")
        jsonl_path = logs_dir / inputs_name
        if not jsonl_path.is_file():
            raise SystemExit(f"inference_inputs not found: {jsonl_path}")
        episode = int(clip.get("episode", -1))
        if episode < 0:
            raise SystemExit(f"Clip missing episode: {clip}")
        overlay_name = clip.get("overlay")
        overlay_path = logs_dir / overlay_name if overlay_name else None
        block_label = clip.get("block_label")
        print(
            f"  clip {clip_idx}/{len(clips)}: ep={episode} "
            f"({clip.get('block_label', '')})",
            flush=True,
        )
        _play_episode(
            args,
            jsonl_path=jsonl_path,
            episode=episode,
            overlay_path=overlay_path if overlay_path and overlay_path.is_file() else None,
            block_label=block_label,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Play inference playlist or episode (jsonl replay)")
    parser.add_argument(
        "input",
        nargs="?",
        help="YYYYMMDD_playlist.json или опустить при --episode + --inputs",
    )
    parser.add_argument("--game", default="rushn_attack")
    parser.add_argument("--mission", default="m1")
    parser.add_argument("--inputs", type=Path, default=None, help="inference_inputs.jsonl (single episode)")
    parser.add_argument("--episode", type=int, default=None, help="номер эпизода для --inputs")
    parser.add_argument("--overlay", type=Path, default=None, help="overlay.json для single episode")
    parser.add_argument("--turbo", action="store_true", help="макс. скорость (nothrottle)")
    parser.add_argument("--timeout", type=float, default=120.0, help="минимальный timeout (сек)")
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="не вызывать playback preflight",
    )
    args = parser.parse_args()

    if not args.skip_preflight:
        from inference_preflight import require_playback_preflight  # noqa: WPS433

        require_playback_preflight(label="play_inference_fm2")

    if args.inputs and args.episode is not None:
        jsonl = _resolve_input_path(args.inputs, args.game, args.mission)
        if not jsonl.is_file():
            raise SystemExit(f"Inputs not found: {jsonl}")
        overlay = Path(args.overlay) if args.overlay else None
        if overlay:
            overlay = _resolve_input_path(overlay, args.game, args.mission)
        _play_episode(args, jsonl_path=jsonl, episode=args.episode, overlay_path=overlay)
        return

    if not args.input:
        raise SystemExit("Provide playlist.json or --inputs + --episode")

    input_path = _resolve_input_path(Path(args.input), args.game, args.mission)
    if not input_path.is_file():
        raise SystemExit(f"Input not found: {input_path}")

    if input_path.suffix.lower() == ".json" and input_path.name.endswith("_playlist.json"):
        _play_playlist(args, input_path)
    else:
        raise SystemExit("Expected YYYYMMDD_playlist.json or use --inputs + --episode")


if __name__ == "__main__":
    main()
