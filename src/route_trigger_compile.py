"""Компиляция RAM-триггеров CP из якорей manifest + scout jsonl."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from playthrough_build import load_head_save_states
from project_paths import (
    game_dir,
    load_yaml,
    ram_scout_jsonl_path,
    route_triggers_path,
)
from ram_map_load import load_ram_addresses
from ram_resolve import load_frames

_RAM_TRIGGER_KEYS = frozenset({"room"})
_KNOWN_MODES = frozenset({"exact", "min_threshold", "max_threshold"})


def route_trigger_compile_config_path(game_id: str, mission: Path) -> Path | None:
    mission_cfg = mission / "config" / "route_trigger_compile.yaml"
    if mission_cfg.is_file():
        return mission_cfg
    game_yaml = load_yaml(game_dir(game_id) / "game.yaml")
    rel = game_yaml.get("route_trigger_compile") or "route_trigger_compile.yaml"
    game_cfg = game_dir(game_id) / str(rel)
    if game_cfg.is_file():
        return game_cfg
    return None


def load_route_trigger_compile_config(game_id: str, mission: Path) -> dict[str, Any]:
    path = route_trigger_compile_config_path(game_id, mission)
    if path is None:
        raise FileNotFoundError(
            f"route_trigger_compile.yaml not found for mission {mission.as_posix()} "
            f"(mission config/ or games/{game_id}/)"
        )
    data = load_yaml(path)
    fields = data.get("fields")
    if not isinstance(fields, dict) or not fields:
        raise ValueError(f"{path}: fields mapping is required")
    for field, spec in fields.items():
        if not isinstance(spec, dict):
            raise ValueError(f"{path}: fields.{field} must be a mapping")
        mode = spec.get("mode")
        if mode not in _KNOWN_MODES:
            raise ValueError(
                f"{path}: fields.{field}.mode must be one of {sorted(_KNOWN_MODES)}, got {mode!r}"
            )
    return data


def _ram_byte(ram_hex: str, addr: int) -> int:
    return bytes.fromhex(ram_hex)[addr]


def _decode_ram_fields(ram_hex: str, addrs: dict[str, int], field_names: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name in field_names:
        if name not in addrs:
            raise ValueError(f"ram_resolve missing field {name!r}")
        val = _ram_byte(ram_hex, addrs[name])
        if name == "room":
            out[name] = f"0x{val:02X}"
        else:
            out[name] = int(val)
    return out


def _apply_field_rule(field: str, value: Any, mode: str, *, spec: dict[str, Any]) -> dict[str, Any]:
    if mode == "exact":
        if field == "room":
            return {"room": str(value)}
        return {field: int(value)}
    if mode == "min_threshold":
        threshold = int(value)
        floor = spec.get("min_floor")
        if floor is not None:
            threshold = max(threshold, int(floor))
        return {f"min_{field}": threshold}
    if mode == "max_threshold":
        return {f"max_{field}": int(value)}
    raise ValueError(f"unsupported compile mode: {mode!r}")


def compile_trigger_from_ram(
    ram_fields: dict[str, Any],
    compile_config: dict[str, Any],
) -> dict[str, Any]:
    trigger: dict[str, Any] = {}
    fields_cfg = compile_config.get("fields") or {}
    for field, spec in fields_cfg.items():
        if field not in ram_fields:
            raise ValueError(f"compile config field {field!r} not present in decoded RAM")
        mode = str(spec.get("mode"))
        trigger.update(_apply_field_rule(field, ram_fields[field], mode, spec=spec))
    return trigger


def anchor_frame_map(head_save_states: dict[str, list[dict]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for items in head_save_states.values():
        for item in items:
            anchor_id = str(item.get("id") or "").strip()
            if not anchor_id:
                continue
            frame = item.get("frame")
            if frame is None:
                continue
            out[anchor_id] = int(frame)
    return out


def _frame_row(frames: list[dict], frame: int) -> dict:
    for row in frames:
        if int(row["frame"]) == int(frame):
            return row
    raise ValueError(f"frame {frame} not found in scout jsonl")


def _ram_keys_in_trigger(trigger: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for key in trigger:
        if key in ("flag", "requires_checkpoint"):
            continue
        if key in _RAM_TRIGGER_KEYS or key.startswith("min_") or key.startswith("max_") or key in ("x", "y"):
            keys.append(key)
    return keys


def list_route_anchors(routes: dict[str, Any]) -> list[str]:
    """Anchor id из checkpoints (без проверки inline RAM)."""
    return [str(cp["anchor"]) for cp in routes.get("checkpoints") or [] if cp.get("anchor")]


def assert_routes_ready_for_compile(routes: dict[str, Any]) -> list[str]:
    """Проверить, что routes.yaml не смешивает anchor с inline RAM (перед compile)."""
    anchors = list_route_anchors(routes)
    for cp in routes.get("checkpoints") or []:
        if cp.get("anchor"):
            continue
        trigger = cp.get("trigger") or {}
        if _ram_keys_in_trigger(trigger):
            raise ValueError(
                f"checkpoint id={cp.get('id')}: inline RAM trigger in routes.yaml; "
                "use anchor + compile_route_triggers, or flag-only trigger"
            )
    return anchors


def validate_routes_for_compile(routes: dict[str, Any]) -> list[str]:
    """Список anchor id для компиляции (с проверкой отсутствия inline RAM)."""
    return assert_routes_ready_for_compile(routes)


def compile_triggers_for_anchors(
    *,
    anchors: list[str],
    anchor_frames: dict[str, int],
    frames: list[dict],
    addrs: dict[str, int],
    compile_config: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    field_names = list((compile_config.get("fields") or {}).keys())
    triggers: dict[str, dict[str, Any]] = {}
    for anchor in anchors:
        frame = anchor_frames.get(anchor)
        if frame is None:
            raise ValueError(
                f"anchor {anchor!r}: no frame in playthrough_manifest head_save_states "
                "(fill frames on protocol phase E)"
            )
        row = _frame_row(frames, frame)
        ram_fields = _decode_ram_fields(row["ram_hex"], addrs, field_names)
        triggers[anchor] = compile_trigger_from_ram(ram_fields, compile_config)
    return triggers


def write_route_triggers(
    mission: Path,
    triggers: dict[str, dict[str, Any]],
    *,
    metadata: dict[str, Any],
) -> Path:
    path = route_triggers_path(mission)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"compiled_from": metadata, "triggers": triggers}
    path.write_text(yaml.dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def compile_for_mission(
    mission: Path,
    game_id: str,
    *,
    fm2_rel: str | None = None,
) -> Path:
    routes_path = mission / "config" / "routes.yaml"
    if not routes_path.is_file():
        raise FileNotFoundError(f"routes.yaml not found: {routes_path}")
    routes = load_yaml(routes_path)
    anchors = validate_routes_for_compile(routes)
    if not anchors:
        raise ValueError(f"{routes_path}: no checkpoints with anchor to compile")

    head_saves = load_head_save_states(mission)
    if not head_saves:
        raise ValueError("playthrough_manifest.yaml: head_save_states required for compile")

    scout_path = ram_scout_jsonl_path(mission)
    if not scout_path.is_file():
        raise FileNotFoundError(f"ram_scout.jsonl not found: {scout_path} (run ram_scout.py first)")

    compile_config = load_route_trigger_compile_config(game_id, mission)
    addrs = load_ram_addresses(mission)
    frames = load_frames(scout_path)
    frames_map = anchor_frame_map(head_saves)

    manifest_path = mission / "config" / "playthrough_manifest.yaml"
    manifest = load_yaml(manifest_path) if manifest_path.is_file() else {}
    if fm2_rel is None:
        fm2_rel = str(manifest.get("fm2_file") or "reference/clear.fm2")

    triggers = compile_triggers_for_anchors(
        anchors=anchors,
        anchor_frames=frames_map,
        frames=frames,
        addrs=addrs,
        compile_config=compile_config,
    )
    metadata = {
        "fm2_file": fm2_rel,
        "scout": scout_path.relative_to(mission).as_posix(),
        "manifest": manifest_path.relative_to(mission).as_posix(),
    }
    return write_route_triggers(mission, triggers, metadata=metadata)


def validate_route_triggers_for_train(mission: Path, game_id: str) -> None:
    """Fail fast перед train, если routes с anchor без актуального route_triggers.yaml."""
    del game_id
    routes_path = mission / "config" / "routes.yaml"
    if not routes_path.is_file():
        return
    routes = load_yaml(routes_path)
    anchors = list_route_anchors(routes)
    if not anchors:
        return

    triggers_file = route_triggers_path(mission)
    if not triggers_file.is_file():
        raise ValueError(
            f"{triggers_file} missing: routes.yaml uses anchor CP. "
            "Run scripts/compile_route_triggers.py (protocol phase E′) before train."
        )

    data = load_yaml(triggers_file)
    compiled = data.get("triggers") or {}
    missing = [a for a in anchors if a not in compiled]
    if missing:
        raise ValueError(
            f"{triggers_file}: missing triggers for anchors {missing}. "
            "Re-run compile_route_triggers.py."
        )

    manifest_path = mission / "config" / "playthrough_manifest.yaml"
    if manifest_path.is_file():
        manifest = load_yaml(manifest_path)
        expected_fm2 = str(manifest.get("fm2_file") or "reference/clear.fm2")
        compiled_from = data.get("compiled_from") or {}
        actual_fm2 = str(compiled_from.get("fm2_file") or "")
        if actual_fm2 and actual_fm2 != expected_fm2:
            raise ValueError(
                f"{triggers_file} compiled for fm2 {actual_fm2!r}, "
                f"manifest expects {expected_fm2!r}. Re-run compile_route_triggers.py."
            )
