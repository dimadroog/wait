#!/usr/bin/env python3
"""Фасад: сводка noop_frac / гистограммы из inference_inputs.jsonl."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from inference_action_stats import format_summary_text, summarize_path  # noqa: E402
from project_paths import repo_root  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(
        description="Summarize noop_frac and action histogram from inference_inputs.jsonl"
    )
    p.add_argument(
        "path",
        help="path to inference_inputs.jsonl or a day-log directory containing it",
    )
    p.add_argument(
        "--attempts",
        default=None,
        help="optional attempts.jsonl (default: sibling of inputs if present)",
    )
    p.add_argument(
        "--json",
        metavar="OUT",
        nargs="?",
        const="-",
        default=None,
        help="write JSON to OUT path, or stdout if OUT omitted / '-'",
    )
    args = p.parse_args()

    root = repo_root()
    path = Path(args.path)
    if not path.is_absolute():
        path = root / path
    attempts: Path | None = None
    if args.attempts:
        attempts = Path(args.attempts)
        if not attempts.is_absolute():
            attempts = root / attempts

    summary = summarize_path(path, attempts=attempts)

    if args.json is not None:
        payload = json.dumps(summary, ensure_ascii=False, indent=2)
        if args.json in ("-", ""):
            print(payload)
        else:
            out = Path(args.json)
            if not out.is_absolute():
                out = root / out
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(payload + "\n", encoding="utf-8")
            print(f"wrote {out}", file=sys.stderr)
        return 0

    print(format_summary_text(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
