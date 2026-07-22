"""Сводка действий из inference_inputs.jsonl (noop_frac, гистограмма).

Нейтральные поля jsonl; без игровых room/CP в логике ядра.
Опционально стыкует attempts.jsonl по episode → max_checkpoint.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        raise FileNotFoundError(f"jsonl not found: {path}")
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def resolve_inputs_path(path: Path) -> Path:
    """Файл jsonl или каталог дня логов (ищет inference_inputs.jsonl)."""
    if path.is_file():
        return path
    if path.is_dir():
        candidate = path / "inference_inputs.jsonl"
        if candidate.is_file():
            return candidate
        raise FileNotFoundError(f"inference_inputs.jsonl not found in {path}")
    raise FileNotFoundError(f"path not found: {path}")


def resolve_attempts_path(inputs_path: Path, attempts: Path | None = None) -> Path | None:
    if attempts is not None:
        return attempts if attempts.is_file() else None
    sibling = inputs_path.parent / "attempts.jsonl"
    return sibling if sibling.is_file() else None


def is_noop_action(action: Any) -> bool:
    if action is None:
        return True
    return str(action).strip() == ""


def summarize_inference_actions(
    input_rows: list[dict[str, Any]],
    *,
    attempt_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Считает noop_frac, гистограмму action и опц. max_checkpoint из attempts."""
    n = len(input_rows)
    noop = sum(1 for r in input_rows if is_noop_action(r.get("action")))
    hist = Counter(str(r.get("action") or "") for r in input_rows)
    # пустой ключ читаемее как ""
    action_hist = {("" if k == "" else k): v for k, v in hist.most_common()}

    by_episode: dict[int, dict[str, int]] = {}
    for r in input_rows:
        ep = int(r.get("episode", 0))
        slot = by_episode.setdefault(ep, {"steps": 0, "noop": 0})
        slot["steps"] += 1
        if is_noop_action(r.get("action")):
            slot["noop"] += 1

    episodes_out: list[dict[str, Any]] = []
    attempts_by_ep: dict[int, dict[str, Any]] = {}
    if attempt_rows:
        for a in attempt_rows:
            ep = int(a.get("episode", 0))
            attempts_by_ep[ep] = a

    for ep in sorted(by_episode):
        slot = by_episode[ep]
        steps = slot["steps"]
        ep_noop = slot["noop"]
        row: dict[str, Any] = {
            "episode": ep,
            "steps": steps,
            "noop": ep_noop,
            "noop_frac": round(ep_noop / steps, 4) if steps else None,
        }
        att = attempts_by_ep.get(ep)
        if att is not None and "max_checkpoint" in att:
            row["max_checkpoint"] = att.get("max_checkpoint")
        episodes_out.append(row)

    max_cps = [e["max_checkpoint"] for e in episodes_out if "max_checkpoint" in e]
    out: dict[str, Any] = {
        "n_steps": n,
        "noop": noop,
        "noop_frac": round(noop / n, 4) if n else None,
        "action_hist": action_hist,
        "n_episodes": len(by_episode),
        "episodes": episodes_out,
    }
    if max_cps:
        out["max_checkpoint_mean"] = round(sum(float(x) for x in max_cps) / len(max_cps), 4)
        out["max_checkpoint_max"] = max(int(x) for x in max_cps)
        out["max_checkpoint_min"] = min(int(x) for x in max_cps)
    return out


def summarize_path(
    path: Path,
    *,
    attempts: Path | None = None,
) -> dict[str, Any]:
    inputs_path = resolve_inputs_path(path)
    input_rows = load_jsonl(inputs_path)
    attempts_path = resolve_attempts_path(inputs_path, attempts)
    attempt_rows = load_jsonl(attempts_path) if attempts_path else None
    summary = summarize_inference_actions(input_rows, attempt_rows=attempt_rows)
    summary["inputs_path"] = str(inputs_path)
    if attempts_path:
        summary["attempts_path"] = str(attempts_path)
    return summary


def format_summary_text(summary: dict[str, Any]) -> str:
    lines = [
        f"inputs: {summary.get('inputs_path', '?')}",
        f"steps: {summary['n_steps']}  episodes: {summary['n_episodes']}  "
        f"noop_frac={summary['noop_frac']}  ({summary['noop']}/{summary['n_steps']})",
    ]
    if summary.get("attempts_path"):
        lines.append(f"attempts: {summary['attempts_path']}")
    if "max_checkpoint_mean" in summary:
        lines.append(
            f"max_checkpoint: mean={summary['max_checkpoint_mean']} "
            f"min={summary['max_checkpoint_min']} max={summary['max_checkpoint_max']}"
        )
    hist = summary.get("action_hist") or {}
    if hist:
        lines.append("action_hist:")
        for action, count in list(hist.items())[:20]:
            label = repr(action) if action == "" else action
            lines.append(f"  {label}: {count}")
    return "\n".join(lines)
