"""Чтение и запись config/workspace.yaml (game, mission, save_state)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from project_paths import load_workspace, workspace_config_path


def load_operator_workspace(path: Path | None = None) -> dict[str, Any]:
    """Прочитать workspace; поля game/mission/save_state как строки или пусто."""
    raw = load_workspace(path)
    return {
        "game": _str_or_empty(raw.get("game")),
        "mission": _str_or_empty(raw.get("mission")),
        "save_state": _str_or_empty(raw.get("save_state")),
    }


def save_operator_workspace(
    game: str,
    mission: str,
    save_state: str,
    *,
    path: Path | None = None,
) -> None:
    """Сохранить операторский контекст в workspace.yaml."""
    cfg_path = path if path is not None else workspace_config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "game": game.strip(),
        "mission": mission.strip(),
        "save_state": save_state.strip(),
    }
    header = (
        "# Дефолты game/mission/save_state для CLI и операторского лаунчера.\n"
        "# Контракт: docs/DESIGN.md#контракт-game--mission\n"
    )
    with cfg_path.open("w", encoding="utf-8") as f:
        f.write(header)
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def _str_or_empty(value: object | None) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text
