"""Авто-resolve RAM-полей из ram_scout.jsonl (сборка эталона)."""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

RAM_SIZE = 2048
FIELD_NAMES = ("room", "x", "y", "hp", "lives", "checkpoint")
MIN_CONFIDENCE = 0.35


@dataclass
class AddrStats:
    addr: int
    changes: int = 0
    mean_right: float = 0.0
    mean_left: float = 0.0
    mean_up: float = 0.0
    mean_down: float = 0.0
    decreases: int = 0
    increases: int = 0
    large_jumps: int = 0
    unique_values: set[int] = field(default_factory=set)


@dataclass
class FieldPick:
    name: str
    addr: int | None
    confidence: float
    note: str


def load_frames(jsonl: Path) -> list[dict]:
    frames: list[dict] = []
    with jsonl.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                frames.append(json.loads(line))
    return frames


def _input_keys(inp: str) -> set[str]:
    return set(inp.split("+")) if inp else set()


def collect_stats(frames: list[dict]) -> dict[int, AddrStats]:
    delta_right: dict[int, list[int]] = defaultdict(list)
    delta_left: dict[int, list[int]] = defaultdict(list)
    delta_up: dict[int, list[int]] = defaultdict(list)
    delta_down: dict[int, list[int]] = defaultdict(list)
    stats: dict[int, AddrStats] = {}

    for i in range(1, len(frames)):
        prev = bytes.fromhex(frames[i - 1]["ram_hex"])
        curr = bytes.fromhex(frames[i]["ram_hex"])
        keys = _input_keys(frames[i].get("input", ""))
        for addr in range(RAM_SIZE):
            if prev[addr] == curr[addr]:
                continue
            st = stats.setdefault(addr, AddrStats(addr=addr))
            st.changes += 1
            d = int(curr[addr]) - int(prev[addr])
            st.unique_values.add(int(curr[addr]))
            st.unique_values.add(int(prev[addr]))
            if d < 0:
                st.decreases += 1
            elif d > 0:
                st.increases += 1
            if abs(d) >= 16:
                st.large_jumps += 1
            if "right" in keys:
                delta_right[addr].append(d)
            if "left" in keys:
                delta_left[addr].append(d)
            if "up" in keys:
                delta_up[addr].append(d)
            if "down" in keys:
                delta_down[addr].append(d)

    for addr, st in stats.items():
        st.mean_right = _mean(delta_right.get(addr, []))
        st.mean_left = _mean(delta_left.get(addr, []))
        st.mean_up = _mean(delta_up.get(addr, []))
        st.mean_down = _mean(delta_down.get(addr, []))
    return stats


def _mean(vals: list[int]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def build_candidates(stats: dict[int, AddrStats]) -> list[dict]:
    ranked = sorted(stats.values(), key=lambda s: s.changes, reverse=True)
    top: list[dict] = []
    for st in ranked[:40]:
        if st.changes == 0:
            break
        hint = ""
        if st.mean_right > 0.3:
            hint = "maybe_x_increase"
        elif st.mean_right < -0.3:
            hint = "maybe_x_decrease"
        top.append(
            {
                "address": f"0x{st.addr:04X}",
                "changes": st.changes,
                "mean_delta_on_right": round(st.mean_right, 3),
                "hint": hint,
            }
        )
    return top


def _score_x(st: AddrStats) -> float:
    if st.changes < 100:
        return 0.0
    score = 0.0
    if st.mean_right > 0.15:
        score += min(st.mean_right, 1.5)
    if st.mean_left < -0.15:
        score += min(abs(st.mean_left), 1.5)
    if st.mean_right > 0.1 and st.mean_left < -0.1:
        score += 0.5
    return score / 3.5


def _score_y(st: AddrStats) -> float:
    if st.changes < 50:
        return 0.0
    score = 0.0
    if st.mean_down > 0.15:
        score += min(st.mean_down, 1.5)
    if st.mean_up < -0.15:
        score += min(abs(st.mean_up), 1.5)
    if st.mean_down > 0.1 and st.mean_up < -0.1:
        score += 0.5
    return score / 3.5


def _score_room(st: AddrStats) -> float:
    n_unique = len(st.unique_values)
    if st.changes < 3 or n_unique < 2 or n_unique > 40:
        return 0.0
    if st.changes > 500:
        return 0.0
    score = 0.0
    if 2 <= n_unique <= 25:
        score += 0.4
    if st.large_jumps >= 1:
        score += 0.35
    rarity = 1.0 - min(st.changes / 500.0, 1.0)
    score += rarity * 0.4
    return min(score, 1.0)


def _score_hp(st: AddrStats) -> float:
    if st.changes < 2 or st.changes > 80:
        return 0.0
    if st.decreases < st.increases:
        return 0.0
    score = 0.3
    ratio = st.decreases / max(st.changes, 1)
    score += min(ratio, 1.0) * 0.4
    if len(st.unique_values) <= 16:
        score += 0.2
    return min(score, 1.0)


def _score_lives(st: AddrStats) -> float:
    if st.changes < 1 or st.changes > 15:
        return 0.0
    if st.decreases < st.increases:
        return 0.0
    score = 0.35
    if len(st.unique_values) <= 8:
        score += 0.35
    if st.changes <= 5:
        score += 0.2
    return min(score, 1.0)


def _score_checkpoint(st: AddrStats) -> float:
    if st.changes < 1 or st.changes > 20:
        return 0.0
    if st.increases < st.decreases:
        return 0.0
    score = 0.35
    if len(st.unique_values) <= 10:
        score += 0.3
    if st.changes <= 8:
        score += 0.25
    return min(score, 1.0)


_SCORERS = {
    "x": _score_x,
    "y": _score_y,
    "room": _score_room,
    "hp": _score_hp,
    "lives": _score_lives,
    "checkpoint": _score_checkpoint,
}


def _sanity_x(st: AddrStats, frames: list[dict]) -> bool:
    hits = 0
    for i in range(1, len(frames)):
        if "right" not in _input_keys(frames[i].get("input", "")):
            continue
        prev = int(bytes.fromhex(frames[i - 1]["ram_hex"])[st.addr])
        curr = int(bytes.fromhex(frames[i]["ram_hex"])[st.addr])
        if curr > prev:
            hits += 1
    return hits >= 3


def _sanity_y(st: AddrStats, frames: list[dict]) -> bool:
    hits = 0
    for i in range(1, len(frames)):
        keys = _input_keys(frames[i].get("input", ""))
        if "up" not in keys and "down" not in keys:
            continue
        prev = int(bytes.fromhex(frames[i - 1]["ram_hex"])[st.addr])
        curr = int(bytes.fromhex(frames[i]["ram_hex"])[st.addr])
        if "down" in keys and curr > prev:
            hits += 1
        if "up" in keys and curr < prev:
            hits += 1
    return hits >= 3


def _sanity_room(st: AddrStats, _frames: list[dict]) -> bool:
    return len(st.unique_values) >= 2 and st.large_jumps >= 1


def _sanity_hp(st: AddrStats, _frames: list[dict]) -> bool:
    return st.decreases >= 1


def _sanity_lives(st: AddrStats, _frames: list[dict]) -> bool:
    return st.decreases >= 1 or st.changes >= 1


def _sanity_checkpoint(st: AddrStats, _frames: list[dict]) -> bool:
    return st.increases >= 1


_SANITY = {
    "x": _sanity_x,
    "y": _sanity_y,
    "room": _sanity_room,
    "hp": _sanity_hp,
    "lives": _sanity_lives,
    "checkpoint": _sanity_checkpoint,
}


def resolve_fields(stats: dict[int, AddrStats], frames: list[dict]) -> list[FieldPick]:
    used: set[int] = set()
    picks: list[FieldPick] = []
    all_stats = list(stats.values())

    for name in FIELD_NAMES:
        scorer = _SCORERS[name]
        sanity = _SANITY[name]
        ranked = sorted(all_stats, key=scorer, reverse=True)
        chosen: FieldPick | None = None
        for st in ranked:
            if st.addr in used:
                continue
            conf = scorer(st)
            if conf < MIN_CONFIDENCE:
                break
            if not sanity(st, frames):
                continue
            chosen = FieldPick(
                name=name,
                addr=st.addr,
                confidence=round(conf, 3),
                note="auto",
            )
            used.add(st.addr)
            break
        if chosen is None:
            chosen = FieldPick(name=name, addr=None, confidence=0.0, note="unresolved")
        picks.append(chosen)
    return picks


def write_candidates(candidates_path: Path, frame_count: int, top: list[dict]) -> None:
    candidates_path.write_text(
        json.dumps({"frame_count": frame_count, "candidates": top}, indent=2),
        encoding="utf-8",
    )


def write_resolve_json(resolve_path: Path, picks: list[FieldPick], frame_count: int) -> None:
    resolve_path.write_text(
        json.dumps(
            {
                "frame_count": frame_count,
                "fields": [
                    {
                        "field": p.name,
                        "address": f"0x{p.addr:04X}" if p.addr is not None else None,
                        "confidence": p.confidence,
                        "note": p.note,
                    }
                    for p in picks
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def write_ram_map(
    mission: Path,
    picks: list[FieldPick],
    candidates_rel: str,
    resolve_rel: str,
    candidates: list[dict],
) -> None:
    game_id = mission.parent.parent.name
    lines = [
        f"# {game_id} — {mission.name} — RAM map",
        "",
        "> Сборка эталона: `ram_scout.py` → авто-resolve ниже.",
        "",
        "| Адрес | Поле | Тип | Примечание |",
        "| ----- | ---- | --- | ---------- |",
    ]
    for p in picks:
        if p.addr is not None:
            addr = f"`0x{p.addr:04X}`"
            note = f"{p.note}, confidence {p.confidence:.2f}"
        else:
            addr = "—"
            note = p.note
        lines.append(f"| {addr} | `{p.name}` | u8 | {note} |")

    lines.extend(
        [
            "",
            "## Candidates (auto)",
            "",
            f"> Источник: `{candidates_rel}` · resolve: `{resolve_rel}`",
            "",
            "| Адрес | Смен | hint |",
            "| ----- | ---- | ---- |",
        ]
    )
    for c in candidates[:15]:
        lines.append(f"| `{c['address']}` | {c['changes']} | {c.get('hint', '')} |")
    lines.append("")
    (mission / "ram_map.md").write_text("\n".join(lines), encoding="utf-8")


def run_resolve(jsonl: Path, mission: Path) -> list[FieldPick]:
    """Кандидаты + resolve + ram_map.md."""
    from project_paths import mission_scout_dir, ram_resolve_path, ram_scout_candidates_path

    scout_dir = mission_scout_dir(mission)
    scout_dir.mkdir(parents=True, exist_ok=True)
    candidates_path = ram_scout_candidates_path(mission)
    resolve_path = ram_resolve_path(mission)
    resolve_path.parent.mkdir(parents=True, exist_ok=True)

    frames = load_frames(jsonl)
    empty = [FieldPick(name=n, addr=None, confidence=0.0, note="unresolved") for n in FIELD_NAMES]
    if len(frames) < 2:
        write_candidates(candidates_path, len(frames), [])
        return empty

    stats = collect_stats(frames)
    top = build_candidates(stats)
    write_candidates(candidates_path, len(frames), top)
    picks = resolve_fields(stats, frames)
    write_resolve_json(resolve_path, picks, len(frames))
    write_ram_map(
        mission,
        picks,
        candidates_path.relative_to(mission).as_posix(),
        resolve_path.relative_to(mission).as_posix(),
        top,
    )
    return picks
