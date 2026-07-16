"""Сборка эталона из FM2 + ram_scout.jsonl + ram_resolve."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import yaml

from etalon_build_config import (
    checkpoint_heuristics_from_etalon_build,
    checkpoint_names_from_etalon_build,
    segment_count_from_etalon_build,
    transition_rooms_from_etalon_build,
)
from project_paths import count_fm2_frames, load_yaml, repo_root
from ram_map_load import load_ram_addresses
from ram_resolve import load_frames

NES_BUTTONS = ("right", "left", "up", "down", "A", "B", "start", "select")


def input_to_action(inp: str) -> str:
    return inp or ""


def encode_action(inp: str) -> int:
    keys = set(inp.split("+")) if inp else set()
    code = 0
    for i, k in enumerate(NES_BUTTONS):
        if k in keys:
            code |= 1 << i
    return code


def _ram_byte(ram_hex: str, addr: int) -> int:
    return bytes.fromhex(ram_hex)[addr]


def build_human_playthrough(frames: list[dict], addrs: dict[str, int]) -> list[dict]:
    rows: list[dict] = []
    for f in frames:
        ram = f["ram_hex"]
        rows.append(
            {
                "frame": f["frame"],
                "room": f"0x{_ram_byte(ram, addrs['room']):02X}",
                "x": _ram_byte(ram, addrs["x"]),
                "y": _ram_byte(ram, addrs["y"]),
                "action": input_to_action(f.get("input", "")),
                "hp": _ram_byte(ram, addrs["hp"]),
                "lives": _ram_byte(ram, addrs["lives"]),
                "checkpoint": _ram_byte(ram, addrs["checkpoint"]),
            }
        )
    return rows


def _room_at(frames: list[dict], addrs: dict[str, int], frame: int) -> int:
    for f in frames:
        if f["frame"] == frame:
            return _ram_byte(f["ram_hex"], addrs["room"])
    return _ram_byte(frames[-1]["ram_hex"], addrs["room"])


def _first_frame_matching(
    frames: list[dict], addrs: dict[str, int], predicate, *, after_frame: int = 0
) -> dict | None:
    for f in frames:
        if f["frame"] <= after_frame:
            continue
        room = _ram_byte(f["ram_hex"], addrs["room"])
        x = _ram_byte(f["ram_hex"], addrs["x"])
        y = _ram_byte(f["ram_hex"], addrs["y"])
        if predicate(room, x, y):
            return f
    return None


def _trigger_from_heuristic(
    heuristic: dict,
    frames: list[dict],
    addrs: dict[str, int],
    transition_rooms: frozenset[int],
) -> dict | None:
    kind = heuristic.get("kind")
    if kind == "first_non_transition_room":
        hit = _first_frame_matching(
            frames, addrs, lambda room, _x, _y: room not in transition_rooms
        )
        if hit:
            room = _ram_byte(hit["ram_hex"], addrs["room"])
            return {"room": f"0x{room:02X}"}
        return None

    if kind == "first_room":
        want = int(str(heuristic["room"]), 16)
        hit = _first_frame_matching(
            frames, addrs, lambda room, _x, _y, w=want: room == w
        )
        if hit:
            return {"room": str(heuristic["room"])}
        return None

    if kind == "first_room_min_y":
        want = int(str(heuristic["room"]), 16)
        min_y = int(heuristic["min_y"])
        after_frame = 0
        after_room = heuristic.get("after_first_room")
        if after_room:
            anchor = int(str(after_room), 16)
            mid = _first_frame_matching(
                frames, addrs, lambda room, _x, _y, w=anchor: room == w
            )
            after_frame = mid["frame"] if mid else 0
        hit = _first_frame_matching(
            frames,
            addrs,
            lambda room, _x, y, w=want, my=min_y: room == w and y >= my,
            after_frame=after_frame,
        )
        if hit:
            trig: dict = {"room": str(heuristic["room"])}
            if min_y:
                trig["min_y"] = min_y
            return trig
        return None

    raise ValueError(f"Unknown checkpoint heuristic kind: {kind!r}")


def checkpoint_triggers(
    frames: list[dict],
    addrs: dict[str, int],
    n: int,
    etalon_build: dict,
) -> list[dict]:
    """CP-триггеры по heuristics из etalon_build.yaml (Strategy)."""
    transition_rooms = transition_rooms_from_etalon_build(etalon_build)
    triggers: list[dict] = []
    for heuristic in checkpoint_heuristics_from_etalon_build(etalon_build):
        if len(triggers) >= n:
            break
        trig = _trigger_from_heuristic(heuristic, frames, addrs, transition_rooms)
        if trig:
            triggers.append(trig)

    while len(triggers) < n:
        seg = plan_segments(len(frames), n)[len(triggers)]
        room = _room_at(frames, addrs, seg["frame_start"])
        triggers.append({"room": f"0x{room:02X}"})

    return triggers[:n]


def plan_segments(total_frames: int, n: int) -> list[dict]:
    """N сегментов → CP0..CP(n-1), границы по кадрам."""
    if total_frames < n * 30:
        raise ValueError(f"Too few frames ({total_frames}) for {n} segments")
    chunk = total_frames // n
    segments: list[dict] = []
    for i in range(n):
        start = 1 if i == 0 else i * chunk + 1
        end = total_frames if i == n - 1 else (i + 1) * chunk
        segments.append(
            {
                "id": f"seg_{i + 1:03d}",
                "checkpoint_from": i,
                "checkpoint_to": i + 1,
                "frame_start": start,
                "frame_end": end,
            }
        )
    return segments


def write_human_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_human_playthrough_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _has_gameplay_input(action: str | None) -> bool:
    """Направление / удар — не Start (intro) и не пустой кадр."""
    a = (action or "").lower()
    return any(tok in a for tok in ("right", "left", "up", "down", "+a", "+b", "a+", "b+")) or a in {
        "a",
        "b",
    }


def gameplay_start_frame_from_rows(
    rows: list[dict],
    *,
    transition_rooms: frozenset[int],
    lives_min: int = 1,
    lives_max: int = 9,
) -> int:
    """Первый кадр управляемого gameplay.

    Только ``room ∉ transition_rooms`` недостаточно: на title/attract у Rush'n Attack
    уже бывает ``room=0x00`` при ``lives=0`` и ``x=129`` (ложный gameplay-start @18).
    ``lives`` 1..9 тоже недостаточно: перед уровнем идёт fade (room 0x11→0x01, чёрный
    экран @1226). Нужен ещё кадр с реальным вводом (right/left/…).
    """
    for row in rows:
        room = int(str(row["room"]), 16)
        lives = int(row.get("lives", 0))
        if room in transition_rooms:
            continue
        if not (lives_min <= lives <= lives_max):
            continue
        if not _has_gameplay_input(row.get("action")):
            continue
        return int(row["frame"])
    raise ValueError(
        "No gameplay start frame found in human_playthrough rows "
        f"(need room outside transition, lives in [{lives_min}, {lives_max}], "
        "and a movement/attack action)"
    )


def inference_save_state_plan(gameplay_frame: int) -> list[dict]:
    return [{"frame": gameplay_frame, "file": "inference_cp0.fc0", "slot": 0}]


def write_routes_yaml(
    path: Path,
    game_id: str,
    mission_id: str,
    segments: list[dict],
    frames,
    addrs,
    etalon_build: dict,
) -> None:
    cp_names = checkpoint_names_from_etalon_build(etalon_build)
    checkpoints = []
    triggers = checkpoint_triggers(frames, addrs, len(segments), etalon_build)
    for i, trigger in enumerate(triggers):
        name = cp_names[i] if i < len(cp_names) else f"segment_{i}"
        checkpoints.append({"id": i, "name": name, "trigger": trigger})
    checkpoints.append(
        {
            "id": len(segments),
            "name": "mission_clear",
            "trigger": {"flag": "mission_complete"},
        }
    )
    routes_yaml = {
        "game": game_id,
        "mission": mission_id.replace("m", "") if mission_id.startswith("m") else mission_id,
        "checkpoints": checkpoints,
        "rewards": {
            "default": {
                "checkpoint_bonus": 100,
                "death_penalty": 40,
                "mission_clear_bonus": 1000,
                "step_penalty": 0.005,
                "kill_bonus": 0,
            }
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(routes_yaml, allow_unicode=True, sort_keys=False), encoding="utf-8")


def write_manifest_yaml(
    path: Path,
    *,
    game_id: str,
    mission_id: str,
    fm2_rel: str,
    total_frames: int,
    segments: list[dict],
    frames: list[dict],
    addrs: dict[str, int],
    gameplay_start_frame: int | None = None,
) -> None:
    runtime = load_yaml(repo_root() / "fceux" / "runtime.yaml")
    seg_rows = []
    for i, seg in enumerate(segments):
        rooms = set()
        for f in frames:
            fr = f["frame"]
            if seg["frame_start"] <= fr <= seg["frame_end"]:
                rooms.add(_ram_byte(f["ram_hex"], addrs["room"]))
        seg_rows.append(
            {
                "id": seg["id"],
                "name": seg["id"],
                "checkpoint_from": seg["checkpoint_from"],
                "checkpoint_to": seg["checkpoint_to"],
                "frame_start": seg["frame_start"],
                "frame_end": seg["frame_end"],
                "room_ids": [f"0x{r:02X}" for r in sorted(rooms)[:8]],
                "reference_clear_sec": round((seg["frame_end"] - seg["frame_start"]) / 60.0, 1),
                "demo_file": f"demos/{seg['id']}.npz",
                "save_state": f"states/cp{i}.fc0",
            }
        )
    manifest_yaml = {
        "playthrough_id": Path(fm2_rel).stem,
        "game": game_id,
        "mission": mission_id.replace("m", "") if mission_id.startswith("m") else mission_id,
        "recorded_at": date.today().isoformat(),
        "emulator": "fceux",
        "fceux_version": runtime.get("fceux_version", "2.6.6"),
        "fceux_port": runtime.get("port", "win32"),
        "fm2_file": fm2_rel,
        "total_frames": total_frames,
        "reference_clear_sec": round(total_frames / 60.0, 1),
        "segments": seg_rows,
    }
    if gameplay_start_frame is not None:
        manifest_yaml["inference"] = {
            "gameplay_start_frame": gameplay_start_frame,
            "save_state": "states/inference_cp0.fc0",
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(manifest_yaml, allow_unicode=True, sort_keys=False), encoding="utf-8")


def save_state_plan(segments: list[dict]) -> list[dict]:
    """Кадры и слоты FCEUX (0..4) для save states."""
    return [
        {"frame": seg["frame_start"], "file": f"cp{i}.fc0", "slot": i}
        for i, seg in enumerate(segments)
    ]


def build_playthrough_artifacts(
    mission: Path,
    game_id: str,
    fm2: Path,
    frames: list[dict],
    etalon_build: dict,
) -> tuple[list[dict], list[dict]]:
    addrs = load_ram_addresses(mission)
    rows = build_human_playthrough(frames, addrs)
    n_segments = segment_count_from_etalon_build(etalon_build)
    segments = plan_segments(len(frames), n_segments)
    transition_rooms = transition_rooms_from_etalon_build(etalon_build)
    gameplay_frame = gameplay_start_frame_from_rows(rows, transition_rooms=transition_rooms)

    reference = mission / "reference"
    config = mission / "config"
    write_human_jsonl(reference / "human_playthrough.jsonl", rows)
    fm2_rel = fm2.relative_to(mission).as_posix()
    write_routes_yaml(
        config / "routes.yaml", game_id, mission.name, segments, frames, addrs, etalon_build
    )
    write_manifest_yaml(
        config / "playthrough_manifest.yaml",
        game_id=game_id,
        mission_id=mission.name,
        fm2_rel=fm2_rel,
        total_frames=len(frames),
        segments=segments,
        frames=frames,
        addrs=addrs,
        gameplay_start_frame=gameplay_frame,
    )
    return rows, segments
