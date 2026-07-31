"""Награды по чекпоинтам из config/routes.yaml (+ route_triggers.yaml при anchor CP)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import gymnasium as gym

from project_paths import load_yaml, route_triggers_path


def _norm_room(room: str) -> str:
    return str(room).strip().upper()


def trigger_matches(
    trigger: dict[str, Any],
    ram: dict[str, Any],
    *,
    achieved: set[int] | None = None,
) -> bool:
    if "flag" in trigger:
        flag = trigger["flag"]
        if flag == "mission_complete":
            return bool(ram.get("mission_complete"))
        return False

    req = trigger.get("requires_checkpoint")
    if req is not None:
        if not achieved or int(req) not in achieved:
            return False

    room = trigger.get("room")
    if room is not None and _norm_room(ram.get("room", "")) != _norm_room(room):
        return False

    # min_<field> / max_<field> для любых числовых ключей RAM (x, y, stage, …).
    for key, bound in trigger.items():
        if key in ("room", "flag", "requires_checkpoint"):
            continue
        if key.startswith("min_"):
            field = key[4:]
            try:
                if int(ram.get(field, 0)) < int(bound):
                    return False
            except (TypeError, ValueError):
                return False
        elif key.startswith("max_"):
            field = key[4:]
            try:
                if int(ram.get(field, 0)) > int(bound):
                    return False
            except (TypeError, ValueError):
                return False

    return True


def mission_complete_heuristic(
    ram: dict[str, Any],
    *,
    min_progress_cp: int,
    rules: dict[str, Any] | None,
) -> bool:
    """Финиш миссии по heuristics из config/routes.yaml (игро/миссион-специфично)."""
    if not rules or min_progress_cp < int(rules.get("min_progress_cp", 0)):
        return False
    room = rules.get("room")
    if room is not None and _norm_room(ram.get("room", "")) != _norm_room(str(room)):
        return False
    if "x" in rules and int(ram.get("x", -1)) != int(rules["x"]):
        return False
    y = int(ram.get("y", 0))
    if "min_y" in rules and y < int(rules["min_y"]):
        return False
    if "max_y" in rules and y > int(rules["max_y"]):
        return False
    return True


def _checkpoint_requires(cp: dict[str, Any], trigger: dict[str, Any]) -> int | None:
    if "requires_checkpoint" in cp:
        return int(cp["requires_checkpoint"])
    req = trigger.get("requires_checkpoint")
    return int(req) if req is not None else None


def load_resolved_checkpoints(
    routes_path: str | Path,
    triggers_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Собрать runtime CP: anchor → route_triggers; legacy inline trigger; flag CP."""
    routes = load_yaml(Path(routes_path))
    bindings: dict[str, Any] = {}
    tpath = Path(triggers_path) if triggers_path is not None else route_triggers_path(
        Path(routes_path).parent.parent
    )
    if tpath.is_file():
        bindings = load_yaml(tpath).get("triggers") or {}

    resolved: list[dict[str, Any]] = []
    for cp in routes.get("checkpoints") or []:
        entry = dict(cp)
        anchor = cp.get("anchor")
        inline = dict(cp.get("trigger") or {})
        if anchor:
            anchor_id = str(anchor)
            ram_trig = bindings.get(anchor_id)
            if ram_trig is None:
                raise ValueError(
                    f"checkpoint id={cp.get('id')} anchor={anchor_id!r}: "
                    f"no trigger in {tpath}. Run compile_route_triggers.py."
                )
            trigger = dict(ram_trig)
            req = _checkpoint_requires(cp, inline)
            if req is not None:
                trigger["requires_checkpoint"] = req
            entry["trigger"] = trigger
        elif inline:
            entry["trigger"] = inline
        else:
            entry["trigger"] = {}
        entry.pop("anchor", None)
        resolved.append(entry)
    return sorted(resolved, key=lambda c: int(c["id"]))


class CheckpointRewardWrapper(gym.Wrapper):
    """Читает routes.yaml; награда только за рост max_checkpoint."""

    def __init__(
        self,
        env: gym.Env,
        routes_path: str | Path,
        *,
        triggers_path: str | Path | None = None,
        profile: str = "default",
        reward_overrides: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(env)
        self.routes_path = Path(routes_path)
        if triggers_path is None:
            triggers_path = route_triggers_path(self.routes_path.parent.parent)
        self.triggers_path = Path(triggers_path) if triggers_path else None
        routes = load_yaml(self.routes_path)
        self._checkpoints = load_resolved_checkpoints(self.routes_path, self.triggers_path)
        rewards_root = routes.get("rewards") or {}
        self._rewards = dict(rewards_root.get(profile) or rewards_root.get("default") or {})
        if reward_overrides:
            self._rewards.update(reward_overrides)
        self._profile = profile
        self._heuristics = dict(routes.get("heuristics") or {})

        self.best_checkpoint = -1
        self._achieved: set[int] = set()
        self.episode_reward = 0.0

    def reset(self, **kwargs):
        obs, info = self.env.reset(**kwargs)
        self.best_checkpoint = -1
        self._achieved = set()
        self.episode_reward = 0.0
        info = self._enrich_info(info)
        return obs, info

    def step(self, action):
        obs, _base_reward, terminated, truncated, info = self.env.step(action)
        info = self._enrich_info(info)

        reward = self._compute_reward(info)
        self.episode_reward += reward
        info["episode_reward"] = self.episode_reward

        if info.get("mission_complete"):
            terminated = True

        return obs, reward, terminated, truncated, info

    def _enrich_info(self, info: dict[str, Any]) -> dict[str, Any]:
        ram = dict(info.get("ram") or {})
        max_cp = self._update_checkpoints(ram)

        flag_cp = next(
            (int(cp["id"]) for cp in self._checkpoints if cp.get("trigger", {}).get("flag") == "mission_complete"),
            None,
        )
        mission_done = False
        if flag_cp is not None and flag_cp in self._achieved:
            mission_done = True
        elif mission_complete_heuristic(
            ram,
            min_progress_cp=max_cp,
            rules=self._heuristics.get("mission_complete"),
        ):
            mission_done = True
            if flag_cp is not None:
                self._achieved.add(flag_cp)
                max_cp = max(max_cp, flag_cp)

        info = dict(info)
        info["max_checkpoint"] = max_cp
        info["mission_complete"] = mission_done
        info["achieved_checkpoints"] = sorted(self._achieved)
        return info

    def _update_checkpoints(self, ram: dict[str, Any]) -> int:
        for cp in self._checkpoints:
            cp_id = int(cp["id"])
            if cp_id in self._achieved:
                continue
            trigger = cp.get("trigger") or {}
            if "flag" in trigger:
                continue
            if trigger_matches(trigger, ram, achieved=self._achieved):
                self._achieved.add(cp_id)
        return max(self._achieved) if self._achieved else -1

    def _compute_reward(self, info: dict[str, Any]) -> float:
        r = 0.0
        step_penalty = float(self._rewards.get("step_penalty", 0.0))
        r -= step_penalty

        max_cp = int(info.get("max_checkpoint", -1))
        if max_cp > self.best_checkpoint:
            bonus = float(self._rewards.get("checkpoint_bonus", 100))
            r += bonus * (max_cp - self.best_checkpoint)
            self.best_checkpoint = max_cp

        if info.get("died"):
            r -= float(self._rewards.get("death_penalty", 40))

        if info.get("mission_complete"):
            r += float(self._rewards.get("mission_clear_bonus", 1000))

        hot = self._rewards.get("hot_zone")
        if isinstance(hot, dict):
            ram = info.get("ram") or {}
            x = int(ram.get("x", 0))
            x_from = int(hot.get("x_from", 0))
            x_to = int(hot.get("x_to", 255))
            if x_from <= x <= x_to:
                dx_scale = float(hot.get("dx_scale", 0.0))
                r += dx_scale

        milestone_x = self._rewards.get("milestone_x")
        if milestone_x is not None:
            ram = info.get("ram") or {}
            if int(ram.get("x", 0)) >= int(milestone_x):
                r += float(self._rewards.get("milestone_bonus", 0))

        kill_bonus = float(self._rewards.get("kill_bonus", 0))
        if kill_bonus:
            pass  # выкл

        return r


def load_routes(mission: Path) -> dict[str, Any]:
    path = mission / "config" / "routes.yaml"
    return load_yaml(path) or {}
