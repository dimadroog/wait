"""Сборка эталона из FM2 + ram_scout.jsonl + ram_resolve."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import yaml

from etalon_build_config import (
    REQUIRE_INPUT_MOVE_OR_ATTACK,
    REQUIRE_INPUT_NONE,
    GameplayStartRule,
    checkpoint_heuristics_from_etalon_build,
    checkpoint_names_from_etalon_build,
    gameplay_start_rule_from_etalon_build,
    rewards_default_from_etalon_build,
    segment_count_from_etalon_build,
    transition_rooms_from_etalon_build,
)
from project_paths import count_fm2_frames, demos_for_bc_dir, load_yaml, repo_root
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


def plan_segments(
    total_frames: int,
    n: int,
    *,
    gameplay_start_frame: int | None = None,
) -> list[dict]:
    """N сегментов по кадрам эталона.

    Если задан ``gameplay_start_frame`` (>1):
      - seg_001 = [1 .. gp-1] — до геймплея (title/intro);

      - seg_002..seg_N = равные доли [gp .. total] — прогресс миссии
        (save ``cp0`` .. ``cp{N-2}``).

    Иначе — прежнее равное деление всего фильма (legacy).
    """
    if total_frames < n * 30:
        raise ValueError(f"Too few frames ({total_frames}) for {n} segments")
    gp = None if gameplay_start_frame is None else int(gameplay_start_frame)
    if gp is None or gp <= 1:
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

    if gp >= total_frames:
        raise ValueError(
            f"gameplay_start_frame ({gp}) must be < total_frames ({total_frames})"
        )
    if n < 2:
        raise ValueError("need at least 2 segments when gameplay_start_frame is set")

    segments = [
        {
            "id": "seg_001",
            "checkpoint_from": 0,
            "checkpoint_to": 0,
            "frame_start": 1,
            "frame_end": gp - 1,
        }
    ]
    n_gameplay = n - 1
    span = total_frames - gp + 1
    for i in range(n_gameplay):
        start = gp + (i * span) // n_gameplay
        if i == n_gameplay - 1:
            end = total_frames
        else:
            end = gp + ((i + 1) * span) // n_gameplay - 1
        segments.append(
            {
                "id": f"seg_{i + 2:03d}",
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


def _has_move_or_attack_input(action: str | None) -> bool:
    """Направление или удар; не Start/Select и не пустой кадр."""
    a = (action or "").lower()
    return any(tok in a for tok in ("right", "left", "up", "down", "+a", "+b", "a+", "b+")) or a in {
        "a",
        "b",
    }


def gameplay_start_frame_from_rows(
    rows: list[dict],
    *,
    transition_rooms: frozenset[int],
    rule: GameplayStartRule,
) -> int:
    """Первый кадр управляемого gameplay по правилу из etalon_build (плагин)."""
    for row in rows:
        room = int(str(row["room"]), 16)
        lives = int(row.get("lives", 0))
        if rule.exclude_transition_rooms and room in transition_rooms:
            continue
        if rule.lives_min is not None and rule.lives_max is not None:
            if not (rule.lives_min <= lives <= rule.lives_max):
                continue
        if rule.require_input == REQUIRE_INPUT_MOVE_OR_ATTACK:
            if not _has_move_or_attack_input(row.get("action")):
                continue
        return int(row["frame"])

    parts = []
    if rule.exclude_transition_rooms:
        parts.append("room not in transition_rooms")
    if rule.lives_min is not None:
        parts.append(f"lives in [{rule.lives_min}, {rule.lives_max}]")
    if rule.require_input != REQUIRE_INPUT_NONE:
        parts.append(f"require_input={rule.require_input}")
    raise ValueError(
        "No gameplay start frame found in human_playthrough rows "
        f"(need {', '.join(parts) or 'any frame'})"
    )


def load_head_save_states(mission: Path) -> dict[str, list[dict]] | None:
    """Блок head_save_states из playthrough_manifest (ручные якоря / пилот)."""
    path = mission / "config" / "playthrough_manifest.yaml"
    if not path.is_file():
        return None
    raw = load_yaml(path).get("head_save_states")
    if not isinstance(raw, dict) or not raw:
        return None
    out: dict[str, list[dict]] = {}
    for head, items in raw.items():
        if not isinstance(items, list):
            raise ValueError(f"head_save_states.{head} must be a list")
        out[str(head)] = [dict(x) for x in items]
    return out


def iter_head_save_entries(head_save_states: dict[str, list[dict]]) -> list[dict]:
    """Плоский список слотов, отсортированный по кадру FM2."""
    entries: list[dict] = []
    for head, items in head_save_states.items():
        for item in items:
            if "id" not in item or "frame" not in item:
                raise ValueError(f"head_save_states.{head} entry needs id+frame: {item!r}")
            entries.append({**item, "head": str(head)})
    entries.sort(key=lambda e: int(e["frame"]))
    frames = [int(e["frame"]) for e in entries]
    if len(frames) != len(set(frames)):
        raise ValueError(f"duplicate frames in head_save_states: {frames}")
    return entries


def head_save_state_plan(head_save_states: dict[str, list[dict]]) -> list[dict]:
    """План FCEUX save: ``cp_<head><i>.fc0`` из манифеста (слоты 0..9)."""
    entries = iter_head_save_entries(head_save_states)
    if len(entries) > 10:
        raise ValueError(
            f"head_save_states has {len(entries)} slots; FCEUX supports at most 10 (0..9)"
        )
    return [
        {
            "frame": int(e["frame"]),
            "file": f"{e['id']}.fc0",
            "slot": i,
        }
        for i, e in enumerate(entries)
    ]


def default_gameplay_save_rel(head_save_states: dict[str, list[dict]] | None) -> str:
    """Канон train+inference reset: первый gameplay-слот или первый слот вообще."""
    if not head_save_states:
        return "save_states/cp_gameplay0.fc0"
    gameplay = head_save_states.get("gameplay") or []
    if gameplay:
        return f"save_states/{gameplay[0]['id']}.fc0"
    entries = iter_head_save_entries(head_save_states)
    return f"save_states/{entries[0]['id']}.fc0"


def gameplay_start_frame_from_head_saves(
    head_save_states: dict[str, list[dict]] | None,
) -> int | None:
    if not head_save_states:
        return None
    gameplay = head_save_states.get("gameplay") or []
    if not gameplay:
        return None
    return int(gameplay[0]["frame"])


def nearest_head_save_rel(
    frame: int,
    head_save_states: dict[str, list[dict]] | None,
) -> str | None:
    """Save state с max(frame_slot ≤ frame); иначе None."""
    if not head_save_states:
        return None
    best: dict | None = None
    for e in iter_head_save_entries(head_save_states):
        if int(e["frame"]) <= int(frame):
            best = e
        else:
            break
    if best is None:
        return None
    return f"save_states/{best['id']}.fc0"


def write_routes_yaml(
    path: Path,
    game_id: str,
    mission_id: str,
    segments: list[dict],
    frames,
    addrs,
    etalon_build: dict,
) -> None:
    from route_trigger_compile import (
        compile_triggers_for_anchors,
        load_route_trigger_compile_config,
        write_route_triggers,
    )

    cp_names = checkpoint_names_from_etalon_build(etalon_build)
    checkpoints = []
    anchors: list[str] = []
    for i in range(len(segments)):
        name = cp_names[i] if i < len(cp_names) else f"segment_{i}"
        anchor = f"cp_gameplay{i + 1}"
        anchors.append(anchor)
        checkpoints.append({"id": i + 1, "name": name, "anchor": anchor})
    checkpoints.append(
        {
            "id": len(segments) + 1,
            "name": "mission_clear",
            "trigger": {"flag": "mission_complete"},
        }
    )
    routes_yaml = {
        "game": game_id,
        "mission": mission_id.replace("m", "") if mission_id.startswith("m") else mission_id,
        "checkpoints": checkpoints,
        "rewards": {"default": rewards_default_from_etalon_build(etalon_build)},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(routes_yaml, allow_unicode=True, sort_keys=False), encoding="utf-8")

    mission = path.parent.parent
    compile_config = load_route_trigger_compile_config(game_id, mission)
    anchor_frames = {anchor: int(segments[i]["frame_end"]) for i, anchor in enumerate(anchors)}
    triggers = compile_triggers_for_anchors(
        anchors=anchors,
        anchor_frames=anchor_frames,
        frames=frames,
        addrs=addrs,
        compile_config=compile_config,
    )
    write_route_triggers(
        mission,
        triggers,
        metadata={
            "fm2_file": "reference/clear.fm2",
            "scout": "reference/scout/ram_scout.jsonl",
            "manifest": "config/playthrough_manifest.yaml",
        },
    )


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
    head_save_states: dict[str, list[dict]] | None = None,
) -> None:
    runtime = load_yaml(repo_root() / "fceux" / "runtime.yaml")
    gp = gameplay_start_frame_from_head_saves(head_save_states)
    if gp is not None:
        gameplay_start_frame = gp
    seg_rows = []
    for i, seg in enumerate(segments):
        rooms = set()
        for f in frames:
            fr = f["frame"]
            if seg["frame_start"] <= fr <= seg["frame_end"]:
                rooms.add(_ram_byte(f["ram_hex"], addrs["room"]))
        save_rel = nearest_head_save_rel(int(seg["frame_start"]), head_save_states)
        if save_rel is None:
            save_rel = default_gameplay_save_rel(head_save_states)
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
                "demo_file": f"reference/demos_for_bc/{seg['id']}.npz",
                "save_state": save_rel,
            }
        )
    manifest_yaml: dict = {
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
    if head_save_states:
        manifest_yaml["head_save_states"] = head_save_states
    if gameplay_start_frame is not None:
        save_rel = default_gameplay_save_rel(head_save_states)
        manifest_yaml["train"] = {
            "save_state": save_rel,
            "gameplay_start_frame": int(gameplay_start_frame),
        }
        manifest_yaml["inference"] = {
            "save_state": save_rel,
            "gameplay_start_frame": int(gameplay_start_frame),
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(manifest_yaml, allow_unicode=True, sort_keys=False), encoding="utf-8")


def save_state_plan(
    segments: list[dict],
    *,
    gameplay_start_frame: int | None = None,
    head_save_states: dict[str, list[dict]] | None = None,
) -> list[dict]:
    """Кадры и слоты FCEUX: только ``head_save_states`` → ``cp_<head><i>.fc0``."""
    del segments, gameplay_start_frame  # сегменты не задают имена слотов
    if not head_save_states:
        raise ValueError(
            "head_save_states required in playthrough_manifest.yaml "
            "(manual anchors → cp_<head><i>.fc0)"
        )
    return head_save_state_plan(head_save_states)


def build_playthrough_artifacts(
    mission: Path,
    game_id: str,
    fm2: Path,
    frames: list[dict],
    etalon_build: dict | None,
) -> tuple[list[dict], list[dict]]:
    addrs = load_ram_addresses(mission)
    rows = build_human_playthrough(frames, addrs)
    head_saves = load_head_save_states(mission)
    gameplay_frame = gameplay_start_frame_from_head_saves(head_saves)
    if etalon_build is None:
        if gameplay_frame is None:
            raise ValueError(
                "etalon_build.yaml отсутствует: нужны head_save_states "
                "(cp_gameplay0) в playthrough_manifest.yaml"
            )
        n_segments = 5
    else:
        n_segments = segment_count_from_etalon_build(etalon_build)
        if gameplay_frame is None:
            gameplay_frame = gameplay_start_frame_from_rows(
                rows,
                transition_rooms=transition_rooms_from_etalon_build(etalon_build),
                rule=gameplay_start_rule_from_etalon_build(etalon_build),
            )
    segments = plan_segments(
        len(frames), n_segments, gameplay_start_frame=gameplay_frame
    )

    reference = mission / "reference"
    config = mission / "config"
    write_human_jsonl(reference / "human_playthrough.jsonl", rows)
    fm2_rel = fm2.relative_to(mission).as_posix()
    # Без etalon_build не затираем ручной routes.yaml (канон CP после аудита).
    if etalon_build is not None:
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
        head_save_states=head_saves,
    )
    return rows, segments


def _load_human_jsonl(path: Path) -> dict[int, dict]:
    by_frame: dict[int, dict] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                row = json.loads(line)
                by_frame[row["frame"]] = row
    return by_frame


def npz_is_non_stub(path: Path) -> bool:
    """True если файл — демо с реальными obs (record_demos), не stub segment_playthrough."""
    try:
        with np.load(path, allow_pickle=True) as data:
            if "meta" in data.files:
                raw = data["meta"]
                text = raw.item() if getattr(raw, "shape", ()) == () else str(raw)
                meta = json.loads(str(text))
                if isinstance(meta, dict) and meta.get("obs_stub") is False:
                    return True
                if isinstance(meta, dict) and meta.get("obs_stub") is True:
                    return False
            if "obs" in data.files:
                obs = data["obs"]
                if getattr(obs, "size", 0) and float(np.max(np.abs(obs))) > 0:
                    return True
    except (OSError, ValueError, json.JSONDecodeError, KeyError):
        return False
    return False


def build_demos(mission: Path, *, force: bool = False) -> list[Path]:
    """Нарезать reference/demos_for_bc/seg_*.npz (actions + obs stub) из manifest."""
    manifest_path = mission / "config" / "playthrough_manifest.yaml"
    human_path = mission / "reference" / "human_playthrough.jsonl"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"manifest not found: {manifest_path}")
    if not human_path.is_file():
        raise FileNotFoundError(f"human_playthrough.jsonl not found: {human_path}")

    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    by_frame = _load_human_jsonl(human_path)
    demos_dir = demos_for_bc_dir(mission)
    demos_dir.mkdir(parents=True, exist_ok=True)
    pending: list[tuple[dict, Path, list[int]]] = []
    blocked: list[str] = []

    for seg in manifest.get("segments", []):
        start = int(seg["frame_start"])
        end = int(seg["frame_end"])
        actions: list[int] = []
        for frame in range(start, end + 1):
            row = by_frame.get(frame)
            if row is None:
                continue
            actions.append(encode_action(row.get("action", "")))
        if not actions:
            continue
        out = demos_dir / f"{seg['id']}.npz"
        if out.is_file() and not force and npz_is_non_stub(out):
            blocked.append(out.name)
            continue
        pending.append((seg, out, actions))

    if blocked:
        raise SystemExit(
            "refuse to overwrite non-stub demos (record_demos): "
            + ", ".join(blocked)
            + ". Pass --force to replace with obs stubs."
        )

    written: list[Path] = []
    for seg, out, actions in pending:
        n = len(actions)
        obs = np.zeros((n, 4, 84, 84), dtype=np.float32)
        act = np.array(actions, dtype=np.int64)
        segment_meta_json = json.dumps(
            {
                "segment_id": seg["id"],
                "mission": mission.name,
                "frame_start": int(seg["frame_start"]),
                "frame_end": int(seg["frame_end"]),
                "obs_stub": True,
            }
        )
        np.savez_compressed(out, obs=obs, actions=act, meta=np.array(segment_meta_json))
        written.append(out)
    return written
