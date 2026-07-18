#!/usr/bin/env python3
"""Подготовка FPS train+measure: архив gen0 + runbook команд.

Не запускает train — только проверяет models/gen0.zip и печатает команды.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from project_paths import artifact_quarantine_dir, default_model_zip, mission_dir, repo_root  # noqa: E402

PRIMARY = "gen0.zip"


def _sha256(path: Path, limit: int = 2_000_000) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(limit)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()[:16]


def main() -> int:
    p = argparse.ArgumentParser(description="Prep FPS dual train+measure (no train)")
    p.add_argument("--game", default="rushn_attack")
    p.add_argument("--mission", default="m1")
    p.add_argument(
        "--target-timesteps",
        type=int,
        default=100_000,
        help="цель для resume gen0 (default 100k)",
    )
    p.add_argument(
        "--session",
        default=None,
        help="id сессии metrics в tmp/bench/ (default: fps_r6_YYYYMMDD)",
    )
    args = p.parse_args()

    mission = mission_dir(args.game, args.mission)
    models_dir = mission / "models"
    archive = models_dir / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    session = args.session or f"fps_r6_{stamp}"
    metrics_dir = artifact_quarantine_dir("bench", session)
    metrics_dir.mkdir(parents=True, exist_ok=True)

    primary = default_model_zip(mission)
    report: dict = {
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "mission": str(mission),
        "session": session,
        "metrics_dir": str(metrics_dir),
        "primary": None,
        "commands": [],
    }

    print("=== prep: models/gen0 ===")
    if not primary.is_file():
        print(f"ERROR: primary missing {primary}", file=sys.stderr)
        return 1

    digest = _sha256(primary)
    bak = archive / f"{stamp}_{PRIMARY}"
    if not bak.is_file():
        shutil.copy2(primary, bak)
        side = primary.with_suffix(".train.json")
        if side.is_file():
            shutil.copy2(side, bak.with_suffix(".train.json"))
        print(f"archive: {bak.name}  sha256={digest}")
    else:
        print(f"archive exists: {bak.name}  sha256={digest}")

    side_p = primary.with_suffix(".train.json")
    meta_p = json.loads(side_p.read_text(encoding="utf-8")) if side_p.is_file() else {}
    report["primary"] = {
        "path": str(primary),
        "sha256_16": digest,
        "sidecar": meta_p,
        "planned_target": args.target_timesteps,
    }
    print(
        f"  PRIMARY {PRIMARY}: n_envs={meta_p.get('n_envs')} "
        f"steps={meta_p.get('num_timesteps')}/{meta_p.get('target_timesteps')} "
        f"-> raise to {args.target_timesteps}"
    )

    manifest = metrics_dir / "prep_manifest.json"
    metrics_jsonl = metrics_dir / "rollouts.jsonl"

    cmd_ab = (
        f"./.venv/Scripts/python.exe src/train/train_ppo.py --smoke "
        f"--smoke-session fps_r6_ab_n{{N}} --n-envs {{N}} --timesteps 4096 "
        f"--no-bc --rollout-metrics --rollout-metrics-session fps_r6_ab_n{{N}}"
    )
    cmd_long = (
        f"./scripts/train_local.sh --n-envs 6 --timesteps {args.target_timesteps} "
        f"--save-every 10000 --model-out models/{PRIMARY} "
        f"--rollout-metrics --rollout-metrics-session {session}"
    )
    cmd_parse = (
        f"./.venv/Scripts/python.exe scripts/parse_train_rollouts.py "
        f"--jsonl {metrics_jsonl.relative_to(repo_root())}"
    )

    report["commands"] = {
        "short_ab_template": cmd_ab,
        "long_dual_train": cmd_long,
        "parse_metrics": cmd_parse,
        "note": f"Short A/B: --smoke only (tmp/). Long dual: --model-out models/{PRIMARY}.",
    }

    manifest.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print(f"manifest: {manifest}")
    print()
    print("=== commands ===")
    print("# 0) preflight / optional reboot")
    print("./.venv/Scripts/python.exe scripts/train_preflight.py")
    print()
    print("# 1) short A/B (smoke quarantine; no mission models)")
    print("#    between runs: train_preflight; N in 4 6 8:")
    print(cmd_ab.replace("{N}", "6"))
    print()
    print("# 2) long dual train+measure")
    print(cmd_long)
    print()
    print("# 3) wall_rollout summary")
    print(cmd_parse)
    print()
    print("Done. See docs/tasks/archive/TASK_TRAIN_FPS_DEGRADATION.md section R6.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
