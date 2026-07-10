"""Загрузка RAM-адресов миссии (ram_resolve.json)."""
from __future__ import annotations

import json
from pathlib import Path

from project_paths import ram_resolve_path


def load_ram_addresses(mission: Path) -> dict[str, int]:
    path = ram_resolve_path(mission)
    if not path.is_file():
        raise FileNotFoundError(
            f"ram_resolve.json not found: {path}. Run ram_scout.py first."
        )
    ram_resolve = json.loads(path.read_text(encoding="utf-8"))
    addrs: dict[str, int] = {}
    for field in ram_resolve.get("fields", []):
        addr = field.get("address")
        if addr:
            addrs[field["field"]] = int(addr, 16)
    required = {"room", "x", "y", "hp", "lives", "checkpoint"}
    missing = required - addrs.keys()
    if missing:
        raise ValueError(f"Unresolved RAM fields in {path}: {sorted(missing)}")
    return addrs
