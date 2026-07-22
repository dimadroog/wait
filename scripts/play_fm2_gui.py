#!/usr/bin/env python3
"""Визуальный просмотр self-contained FM2 в окне FCEUX (фаза C1, оператор).

Без turbo / без -noicon: смотреть gameplay с первых кадров.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from fceux_launch import ensure_fceux_sound_on  # noqa: E402
from fm2_export import (  # noqa: E402
    episode_fm2_guid,
    fm2_has_embedded_savestate,
    refresh_fm2_embedded_savestate,
    remap_fm2_guid,
)
from inference_states import resolve_inference_reset_state  # noqa: E402
from project_paths import (  # noqa: E402
    count_fm2_frames,
    mission_dir,
    parse_fm2_rom_basename,
    repo_root,
    resolve_fceux_binary,
    resolve_rom,
)


def _resolve_fm2(path: Path, game: str, mission: str) -> Path:
    if path.is_file():
        return path.resolve()
    candidate = mission_dir(game, mission) / path
    if candidate.is_file():
        return candidate.resolve()
    raise SystemExit(f"FM2 not found: {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Play self-contained FM2 in FCEUX GUI")
    parser.add_argument("fm2", type=Path, help="path to .fm2")
    parser.add_argument("--game", default="rushn_attack")
    parser.add_argument("--mission", default="m1")
    parser.add_argument(
        "--no-refresh-embed",
        action="store_true",
        help="не обновлять savestate из inference_cp0 (играть как в файле)",
    )
    parser.add_argument(
        "--turbo",
        action="store_true",
        help="ускорить replay (по умолчанию realtime для визуальной проверки)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=0.0,
        help="секунд до kill (0 = до конца movie + 5s)",
    )
    args = parser.parse_args()

    fm2 = _resolve_fm2(args.fm2, args.game, args.mission)
    if fm2.suffix.lower() != ".fm2":
        raise SystemExit(f"Not an FM2 file: {fm2}")
    if args.no_refresh_embed and not fm2_has_embedded_savestate(fm2):
        raise SystemExit(f"FM2 has no embedded savestate: {fm2}")

    mission = mission_dir(args.game, args.mission)
    rom = resolve_rom(args.game)
    staging = repo_root() / "tmp" / "play_fm2_gui" / "staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    staged_fm2 = staging / fm2.name
    shutil.copy2(fm2, staged_fm2)
    if not args.no_refresh_embed:
        clip_guid = episode_fm2_guid(salt=f"gui-{fm2.stem}")
        remap_fm2_guid(staged_fm2, clip_guid)
        fc0 = mission / resolve_inference_reset_state(mission, cp_index=0)
        refresh_fm2_embedded_savestate(staged_fm2, fc0, guid=clip_guid)
        print(f"Refreshed embed from {fc0.name}")

    rom_base = parse_fm2_rom_basename(staged_fm2)
    for name in (rom_base, rom_base + ".nes", rom.name):
        shutil.copy2(rom, staging / name)

    frames = count_fm2_frames(staged_fm2)
    timeout = args.timeout if args.timeout > 0 else frames / 60.0 + 30.0

    fceux = resolve_fceux_binary()
    cmd = [str(fceux)]
    if args.turbo:
        cmd.extend(["-turbo", "1", "-nothrottle", "1"])
    cmd.extend(
        [
            "-playmovie",
            staged_fm2.name,
            "-readonly",
            "1",
            rom_base,
        ]
    )

    print(f"Playing {fm2.name} ({frames} frames) — смотрите окно FCEUX", flush=True)
    print(f"  cwd={staging}")
    print(f"  expect: gameplay (мост) с первых кадров, не title «1 PLAYER»", flush=True)

    env = os.environ.copy()
    # Включаем sound: без него FCEUX часто теряет throttle (replay «в turbo»).
    ensure_fceux_sound_on(fceux.parent)
    proc = subprocess.Popen(cmd, cwd=str(staging), env=env)
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)
        print(f"Stopped after {timeout:.0f}s (movie may still be playing)", flush=True)
    else:
        print(f"FCEUX exit code {proc.returncode}", flush=True)

    # дать ОС отпустить cwd перед возможным cleanup
    time.sleep(0.2)


if __name__ == "__main__":
    main()
