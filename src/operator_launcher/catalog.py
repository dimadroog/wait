"""Enum-источники для UI: игры, миссии, save states, модели, reward profiles."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from inference_states import resolve_inference_reset_state
from playthrough_build import load_head_save_states
from project_paths import game_dir, load_yaml, mission_dir, repo_root


@dataclass(frozen=True)
class GameEntry:
    game_id: str
    title: str

    @property
    def label(self) -> str:
        if self.title and self.title != self.game_id:
            return f"{self.title} ({self.game_id})"
        return self.game_id


@dataclass(frozen=True)
class SaveStateEntry:
    rel_path: str
    label: str
    head: str
    anchor_id: str

    @property
    def display(self) -> str:
        return f"{self.label} — {self.rel_path}"


def list_games() -> list[GameEntry]:
    games_root = repo_root() / "games"
    if not games_root.is_dir():
        return []
    entries: list[GameEntry] = []
    for game_yaml in sorted(games_root.glob("*/game.yaml")):
        data = load_yaml(game_yaml)
        game_id = str(data.get("game_id") or game_yaml.parent.name).strip()
        if not game_id:
            continue
        title = str(data.get("title") or game_id).strip()
        entries.append(GameEntry(game_id=game_id, title=title))
    return entries


def list_missions(game_id: str) -> list[str]:
    missions_root = game_dir(game_id) / "missions"
    if not missions_root.is_dir():
        return []
    return sorted(p.name for p in missions_root.iterdir() if p.is_dir())


def default_mission(game_id: str, workspace_mission: str = "") -> str:
    if workspace_mission.strip():
        return workspace_mission.strip()
    game_yaml = load_yaml(game_dir(game_id) / "game.yaml")
    dm = str(game_yaml.get("default_mission") or "").strip()
    missions = list_missions(game_id)
    if dm and dm in missions:
        return dm
    return missions[0] if missions else ""


def _anchor_labels(mission: Path) -> dict[str, str]:
    routes_path = mission / "config" / "routes.yaml"
    if not routes_path.is_file():
        return {}
    routes = load_yaml(routes_path)
    labels: dict[str, str] = {}
    for cp in routes.get("checkpoints") or []:
        if not isinstance(cp, dict):
            continue
        anchor = str(cp.get("anchor") or "").strip()
        if not anchor:
            continue
        name = str(cp.get("name") or anchor).strip()
        labels[anchor] = name
    return labels


def list_save_state_anchors(game_id: str, mission_id: str) -> list[SaveStateEntry]:
    mission = mission_dir(game_id, mission_id)
    heads = load_head_save_states(mission)
    if not heads:
        return []
    anchor_labels = _anchor_labels(mission)
    entries: list[SaveStateEntry] = []
    for head, items in heads.items():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            anchor_id = str(item.get("id") or "").strip()
            if not anchor_id:
                continue
            rel = f"save_states/{anchor_id}.fc0"
            label = anchor_labels.get(anchor_id) or str(item.get("label") or anchor_id)
            entries.append(
                SaveStateEntry(
                    rel_path=rel,
                    label=label,
                    head=str(head),
                    anchor_id=anchor_id,
                )
            )
    entries.sort(key=lambda e: (e.head, e.anchor_id))
    return entries


def default_save_state(
    game_id: str,
    mission_id: str,
    workspace_save_state: str = "",
) -> str:
    if workspace_save_state.strip():
        rel = workspace_save_state.strip()
        mission = mission_dir(game_id, mission_id)
        if (mission / rel).is_file() or list_save_state_anchors(game_id, mission_id):
            return rel
    mission = mission_dir(game_id, mission_id)
    try:
        return resolve_inference_reset_state(mission)
    except FileNotFoundError:
        anchors = list_save_state_anchors(game_id, mission_id)
        if anchors:
            return anchors[0].rel_path
        return "save_states/cp_gameplay0.fc0"


def list_model_zips(game_id: str, mission_id: str) -> list[str]:
    models_dir = mission_dir(game_id, mission_id) / "models"
    if not models_dir.is_dir():
        return []
    names: list[str] = []
    for path in sorted(models_dir.glob("*.zip")):
        name = path.name
        if name.endswith(".prev.zip"):
            continue
        if name.startswith("smoke_"):
            continue
        names.append(name)
    return names


def model_out_rel(model_name: str) -> str:
    name = model_name.strip()
    if name.startswith("models/"):
        return name
    return f"models/{name}"


def default_replay_input(game_id: str, mission_id: str, model_name: str) -> str:
    """Первый .fm2 в logs/<stem>/, иначе пустая строка (оператор выбирает файл)."""
    stem = Path(model_name).stem
    logs = mission_dir(game_id, mission_id) / "logs" / stem
    if logs.is_dir():
        fm2s = sorted(logs.glob("*.fm2"))
        if fm2s:
            return f"logs/{stem}/{fm2s[0].name}"
    return ""


def list_reward_profiles(game_id: str, mission_id: str) -> list[str]:
    routes_path = mission_dir(game_id, mission_id) / "config" / "routes.yaml"
    if not routes_path.is_file():
        return ["default"]
    routes = load_yaml(routes_path)
    rewards = routes.get("rewards")
    if isinstance(rewards, dict) and rewards:
        return sorted(str(k) for k in rewards)
    return ["default"]


def list_bc_demos(game_id: str, mission_id: str) -> list[str]:
    demos_dir = mission_dir(game_id, mission_id) / "reference" / "demos_for_bc"
    if not demos_dir.is_dir():
        return []
    return sorted(
        f"reference/demos_for_bc/{p.name}"
        for p in demos_dir.glob("seg_*.npz")
        if p.is_file()
    )
