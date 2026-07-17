#!/usr/bin/env python3
"""Подготовка раунда R6 (ISSUE_TRAIN_FPS_DEGRADATION): защита чекпоинтов + runbook.

Не запускает train — только копирует/проверяет артефакты и печатает команды.
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

from project_paths import artifact_quarantine_dir, mission_dir, repo_root  # noqa: E402

# Замороженные артефакты — не перезаписывать раундом R6.
FROZEN = ("m1_v0.zip", "m1_v0_fps_t5.zip")
# Боевая линия n=6: копия fps_t5, дальше только resume с raised target.
PRIMARY = "m1_v0_n6.zip"
SOURCE = "m1_v0_fps_t5.zip"


def _sha256(path: Path, limit: int = 2_000_000) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(limit)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()[:16]


def _copy_checkpoint(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    side_src = src.with_suffix(".train.json")
    side_dst = dst.with_suffix(".train.json")
    if side_src.is_file():
        shutil.copy2(side_src, side_dst)


def main() -> int:
    p = argparse.ArgumentParser(description="Prep R6 dual train+measure (no train)")
    p.add_argument("--game", default="rushn_attack")
    p.add_argument("--mission", default="m1")
    p.add_argument(
        "--force-promote",
        action="store_true",
        help=f"перезаписать {PRIMARY} из {SOURCE} (опасно, если уже учили дальше)",
    )
    p.add_argument(
        "--target-timesteps",
        type=int,
        default=100_000,
        help="цель для боевого resume n=6 (default 100k ≈ ещё ~2–4 ч)",
    )
    p.add_argument(
        "--session",
        default=None,
        help="id сессии metrics в tmp/bench/ (default: fps_r6_YYYYMMDD)",
    )
    args = p.parse_args()

    mission = mission_dir(args.game, args.mission)
    ckpt_dir = mission / "checkpoints"
    archive = ckpt_dir / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    session = args.session or f"fps_r6_{stamp}"
    metrics_dir = artifact_quarantine_dir("bench", session)
    metrics_dir.mkdir(parents=True, exist_ok=True)

    report: dict = {
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "mission": str(mission),
        "session": session,
        "metrics_dir": str(metrics_dir),
        "frozen": {},
        "primary": None,
        "commands": [],
    }

    print("=== R6 prep: protect checkpoints ===")
    for name in FROZEN:
        z = ckpt_dir / name
        if not z.is_file():
            print(f"WARNING: frozen missing: {z}")
            report["frozen"][name] = None
            continue
        digest = _sha256(z)
        bak = archive / f"{stamp}_{name}"
        if not bak.is_file():
            shutil.copy2(z, bak)
            side = z.with_suffix(".train.json")
            if side.is_file():
                shutil.copy2(side, bak.with_suffix(".train.json"))
            print(f"archive: {bak.name}  sha256={digest}")
        else:
            print(f"archive exists: {bak.name}  sha256={digest}")
        side = z.with_suffix(".train.json")
        meta = json.loads(side.read_text(encoding="utf-8")) if side.is_file() else {}
        report["frozen"][name] = {
            "path": str(z),
            "sha256_16": digest,
            "archive": str(bak),
            "sidecar": meta,
        }
        print(
            f"  FROZEN {name}: n_envs={meta.get('n_envs')} "
            f"steps={meta.get('num_timesteps')}/{meta.get('target_timesteps')}"
        )

    src = ckpt_dir / SOURCE
    primary = ckpt_dir / PRIMARY
    if not src.is_file():
        print(f"ERROR: source missing {src} - net linii n=6", file=sys.stderr)
        return 1

    if primary.is_file() and not args.force_promote:
        print(f"primary exists (keep): {primary}")
    else:
        if primary.is_file() and args.force_promote:
            print(f"force-promote: overwrite {primary} from {SOURCE}")
        else:
            print(f"promote: {SOURCE} -> {PRIMARY}")
        _copy_checkpoint(src, primary)

    side_p = primary.with_suffix(".train.json")
    meta_p = json.loads(side_p.read_text(encoding="utf-8")) if side_p.is_file() else {}
    if int(meta_p.get("n_envs", -1)) != 6:
        print(
            f"ERROR: {PRIMARY} sidecar n_envs={meta_p.get('n_envs')} - need 6",
            file=sys.stderr,
        )
        return 1

    report["primary"] = {
        "path": str(primary),
        "sha256_16": _sha256(primary),
        "sidecar": meta_p,
        "planned_target": args.target_timesteps,
    }
    print(
        f"  PRIMARY {PRIMARY}: steps={meta_p.get('num_timesteps')}/"
        f"{meta_p.get('target_timesteps')} -> raise to {args.target_timesteps}"
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
        f"--save-every 10000 --checkpoint-out checkpoints/{PRIMARY} "
        f"--rollout-metrics --rollout-metrics-session {session}"
    )
    # train_local.sh doesn't pass unknown flags to... it does pass "$@"
    # But train_local always adds --n-envs 6 only when no task - good.
    # Wait: `exec "$PY" src/train/train_ppo.py --n-envs 6 "$@"` - if we also pass --n-envs 6 it's fine.
    # rollout-metrics need to be supported - yes we added them.

    cmd_parse = (
        f"./.venv/Scripts/python.exe scripts/parse_train_rollouts.py "
        f"--jsonl {metrics_jsonl.relative_to(repo_root())}"
    )

    report["commands"] = {
        "short_ab_template": cmd_ab,
        "long_dual_train": cmd_long,
        "parse_metrics": cmd_parse,
        "note": (
            "Short A/B: --smoke only (tmp/). Long dual: only "
            f"{PRIMARY}; do not touch {', '.join(FROZEN)}."
        ),
    }

    manifest.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print(f"manifest: {manifest}")
    print()
    print("=== R6 commands ===")
    print("# 0) preflight / optional reboot")
    print("./.venv/Scripts/python.exe scripts/train_preflight.py")
    print()
    print("# 1) short A/B (smoke quarantine; no mission checkpoints)")
    print("#    between runs: train_preflight; N in 4 6 8:")
    print(cmd_ab.replace("{N}", "6"))
    print()
    print("# 2) long dual train+measure (continues n=6 learning)")
    print(cmd_long)
    print()
    print("# 3) wall_rollout summary")
    print(cmd_parse)
    print()
    print("Done. See docs/tasks/TASK_TRAIN_FPS_DEGRADATION.md section R6.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
