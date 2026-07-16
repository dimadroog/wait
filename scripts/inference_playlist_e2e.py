#!/usr/bin/env python3
"""E2E: run_inference → build_playlist → play (BACKLOG 3.4)."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from jsonl_logs import utc_date_prefix  # noqa: E402
from project_paths import artifact_quarantine_dir, cleanup_artifact_quarantine, mission_dir  # noqa: E402


def _py() -> str:
    venv = _REPO / ".venv" / "Scripts" / "python.exe"
    return str(venv if venv.is_file() else Path(sys.executable))


def main() -> int:
    parser = argparse.ArgumentParser(description="E2E inference playlist pipeline")
    parser.add_argument("--game", default="rushn_attack")
    parser.add_argument("--mission", default="m1")
    parser.add_argument("--checkpoint", default="m1_v0.zip")
    parser.add_argument("--episodes", type=int, default=1)
    parser.add_argument("--max-steps", type=int, default=120)
    parser.add_argument("--max-clips", type=int, default=1, help="сколько клипов проиграть из плейлиста")
    parser.add_argument("--play", action="store_true", help="проиграть плейлист после сборки")
    parser.add_argument("--skip-inference", action="store_true", help="только playlist+play из существующих logs")
    args = parser.parse_args()

    py = _py()
    mission = mission_dir(args.game, args.mission)
    logs = mission / "logs"
    date_prefix = utc_date_prefix()
    manifest = logs / f"{date_prefix}_playlist.json"

    bench = artifact_quarantine_dir("bench", "inference_e2e")
    bench.mkdir(parents=True, exist_ok=True)
    report: dict = {"date_prefix": date_prefix, "steps": []}

    try:
        if not args.skip_inference:
            cmd = [
                py,
                str(_REPO / "src" / "stream" / "run_inference.py"),
                "--skip-preflight",
                "--game",
                args.game,
                "--mission",
                args.mission,
                "--checkpoint",
                args.checkpoint,
                "--episodes",
                str(args.episodes),
                "--max-steps",
                str(args.max_steps),
                "--build-playlist",
            ]
            print("E2E: run_inference ...", flush=True)
            proc = subprocess.run(cmd, cwd=str(_REPO), check=False)
            report["steps"].append({"run_inference": proc.returncode})
            if proc.returncode != 0:
                return proc.returncode

        if not manifest.is_file():
            inputs = logs / f"{date_prefix}_inference_inputs.jsonl"
            attempts = logs / f"{date_prefix}_attempts.jsonl"
            if attempts.is_file() and inputs.is_file():
                print("E2E: build_playlist ...", flush=True)
                proc = subprocess.run(
                    [
                        py,
                        str(_REPO / "scripts" / "build_playlist.py"),
                        "--game",
                        args.game,
                        "--mission",
                        args.mission,
                        "--attempts",
                        str(attempts),
                        "--inputs",
                        str(inputs),
                    ],
                    cwd=str(_REPO),
                    check=False,
                )
                report["steps"].append({"build_playlist": proc.returncode})
                if proc.returncode != 0:
                    return proc.returncode

        if not manifest.is_file():
            print(f"E2E FAIL: manifest missing: {manifest}", file=sys.stderr)
            return 2

        clips = json.loads(manifest.read_text(encoding="utf-8")).get("clips") or []
        report["clip_count"] = len(clips)
        report["manifest"] = str(manifest)
        print(f"E2E: manifest OK ({len(clips)} clips)", flush=True)

        if args.play and clips:
            to_play = clips[: max(1, args.max_clips)]
            for clip in to_play:
                ep = int(clip["episode"])
                inputs = logs / clip["inference_inputs"]
                overlay = logs / clip["overlay"] if clip.get("overlay") else None
                cmd = [
                    py,
                    str(_REPO / "scripts" / "play_inference_fm2.py"),
                    "--skip-preflight",
                    "--game",
                    args.game,
                    "--mission",
                    args.mission,
                    "--inputs",
                    str(inputs),
                    "--episode",
                    str(ep),
                ]
                if overlay and overlay.is_file():
                    cmd.extend(["--overlay", str(overlay)])
                print(f"E2E: play episode {ep} ...", flush=True)
                proc = subprocess.run(cmd, cwd=str(_REPO), check=False)
                report["steps"].append({f"play_ep{ep}": proc.returncode})
                if proc.returncode != 0:
                    return proc.returncode

        report_path = bench / "e2e_report.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"E2E PASS — report: {report_path}")
        return 0
    finally:
        cleanup_artifact_quarantine("bench", "inference_e2e")


if __name__ == "__main__":
    raise SystemExit(main())
