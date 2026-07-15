#!/usr/bin/env python3
"""Единый smoke facade (BACKLOG 4.1).

Запускает существующие smoke-скрипты subprocess; cleanup bridge + tmp/smoke в finally.
Не использовать train_ppo для проверки bridge/env.
Suite stress — длительный IPC stress (stress_e2e_gate --quick).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SCRIPTS = _REPO / "scripts"
sys.path.insert(0, str(_REPO / "src"))

from project_paths import (  # noqa: E402
    cleanup_artifact_quarantine,
    cleanup_mission_smoke_checkpoints,
    find_stray_smoke_artifacts,
    mission_dir,
)
from train.env_factory import cleanup_bridge_sessions  # noqa: E402

SUITE_NAMES = ("bridge", "env", "parallel", "stress")


def _suite_commands() -> dict[str, list[str]]:
    """Команды smoke: python + script + args (относительно _REPO)."""
    py = sys.executable
    return {
        "bridge": [py, str(_SCRIPTS / "smoke_bridge.py")],
        "env": [py, str(_SCRIPTS / "smoke_env.py"), "--steps", "20"],
        "parallel": [
            py,
            str(_SCRIPTS / "test_parallel_env.py"),
            "--n-envs",
            "8",
            "--cycles",
            "10",
            "--reset-every",
            "5",
        ],
        "stress": [
            py,
            str(_SCRIPTS / "stress_e2e_gate.py"),
            "--quick",
        ],
    }


def _parse_suites(raw: str) -> list[str]:
    names = [s.strip().lower() for s in raw.split(",") if s.strip()]
    unknown = [n for n in names if n not in SUITE_NAMES]
    if unknown:
        raise SystemExit(f"unknown suite(s): {', '.join(unknown)}; choose from {', '.join(SUITE_NAMES)}")
    if not names:
        raise SystemExit("empty --suite")
    return names


def _run_suite(name: str, cmd: Sequence[str]) -> int:
    print(f"\n=== smoke:{name} ===")
    print(" ".join(cmd))
    result = subprocess.run(cmd, cwd=str(_REPO), check=False)
    if result.returncode == 0:
        print(f"PASS smoke:{name}")
    else:
        print(f"FAIL smoke:{name} (exit {result.returncode})")
    return int(result.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Unified smoke tests (bridge, env, parallel, stress)")
    parser.add_argument(
        "--suite",
        default=",".join(SUITE_NAMES),
        help=f"comma-separated subset (default: all). choices: {', '.join(SUITE_NAMES)}",
    )
    args = parser.parse_args()

    suites = _parse_suites(args.suite)
    commands = _suite_commands()

    cleanup_bridge_sessions("train_")
    cleanup_bridge_sessions("bench_")

    failed: list[str] = []
    try:
        for name in suites:
            rc = _run_suite(name, commands[name])
            if rc != 0:
                failed.append(name)
    finally:
        cleanup_bridge_sessions("train_")
        cleanup_bridge_sessions("bench_")
        cleanup_artifact_quarantine("smoke")
        mission = mission_dir("rushn_attack", "m1")
        removed = cleanup_mission_smoke_checkpoints(mission)
        if removed:
            print(f"removed stray checkpoints: {[str(p) for p in removed]}")
        stray = find_stray_smoke_artifacts(mission)
        if stray:
            print(f"WARN stray smoke artifacts: {[str(p) for p in stray]}")

    print()
    if failed:
        print(f"SMOKE FAIL: {', '.join(failed)}")
        sys.exit(1)
    print("SMOKE OK")


if __name__ == "__main__":
    main()
