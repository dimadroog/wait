#!/usr/bin/env python3
"""Visual probe jsonl replay @ frame N (BACKLOG 3.4 / ISSUE_INFERENCE)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from fm2_playback import gd_screenshot_to_png, ppu_screenshot_heuristic  # noqa: E402
from inference_preflight import warn_portable_movies_pollution  # noqa: E402
from inference_replay import PROBE_RESET_FRAME, probe_inference_replay_ppu  # noqa: E402
from jsonl_logs import utc_date_prefix  # noqa: E402
from project_paths import artifact_quarantine_dir, mission_dir  # noqa: E402
from ram_map_load import load_ram_addresses  # noqa: E402


def _ram_addrs(mission: Path) -> dict[str, int]:
    addrs = load_ram_addresses(mission)
    out: dict[str, int] = {}
    for key in ("room", "x", "lives"):
        raw = addrs[key]
        out[key] = int(str(raw), 16) if str(raw).startswith("0x") else int(raw)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Visual check: jsonl emulation replay")
    parser.add_argument("--game", default="rushn_attack")
    parser.add_argument("--mission", default="m1")
    parser.add_argument("--inputs", type=Path, default=None)
    parser.add_argument("--episode", type=int, default=1)
    parser.add_argument("--probe-at-frame", type=int, default=PROBE_RESET_FRAME)
    parser.add_argument("--timeout", type=float, default=90.0)
    args = parser.parse_args()

    warn_portable_movies_pollution(label="jsonl-visual")
    mission = mission_dir(args.game, args.mission)
    bench = artifact_quarantine_dir("bench", "inference_replay_visual")
    bench.mkdir(parents=True, exist_ok=True)

    inputs = args.inputs
    if inputs is None:
        inputs = mission / "logs" / f"{utc_date_prefix()}_inference_inputs.jsonl"
    inputs = inputs.resolve()
    if not inputs.is_file():
        print(f"missing inputs: {inputs}", file=sys.stderr)
        return 2

    staging = bench / "staging"
    tmp = bench / "tmp"
    shot = bench / f"jsonl_ep{args.episode}_f{args.probe_at_frame}.png"

    result = probe_inference_replay_ppu(
        inputs,
        args.episode,
        staging,
        tmp,
        ram=_ram_addrs(mission),
        probe_at_frame=args.probe_at_frame,
        timeout_sec=args.timeout,
        game=args.game,
        mission=args.mission,
    )

    gd_path = Path(result.get("screenshot_gd_path") or str(shot) + ".gd")
    png_path = shot.with_suffix(".png")
    if gd_screenshot_to_png(gd_path, png_path):
        result["screenshot_png"] = str(png_path)
    ppu = result.get("ppu_heuristic") or ppu_screenshot_heuristic(png_path)

    ram_ok = result.get("gameplay_like_ram") is True
    shot_ok = result.get("screenshot_ok") is True
    ppu_ok = ppu.get("gameplay_like_ppu_heuristic") is True

    summary = {
        "phase": "jsonl_replay_visual",
        "inputs": str(inputs),
        "episode": args.episode,
        "probe_at_frame": args.probe_at_frame,
        "probe": result,
        "verdict": {
            "ram_pass": ram_ok,
            "screenshot_ok": shot_ok,
            "ppu_gameplay": ppu_ok,
            "title_like": ppu.get("title_like"),
            "visual_pass": ram_ok and shot_ok and ppu_ok,
        },
    }
    out_path = bench / "jsonl_replay_visual_results.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"\nscreenshot: {png_path if png_path.is_file() else gd_path}")
    print(f"written: {out_path}")
    return 0 if summary["verdict"]["visual_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
