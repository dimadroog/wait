"""Маппинг phase_id → head_id и predict для Multi-head (TASK_POLICY_SEPARATION)."""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import torch as th
from stable_baselines3 import PPO

from project_paths import game_dir, load_yaml


@dataclass(frozen=True)
class IsolationForbidRule:
    """Запрет: head_id не должен быть активен на phase_id из phases."""

    head: str
    phases: frozenset[str]


@dataclass(frozen=True)
class PolicyHeadsSpec:
    """Манифест голов из YAML плагина (env_config.policy_heads)."""

    default_head: str
    heads: tuple[str, ...]
    phase_to_head: dict[str, str]
    # head_id → разрешённые action strings; None/отсутствует = все действия
    action_masks: dict[str, tuple[str, ...] | None] = field(default_factory=dict)
    # Правила isolation / coverage — только из YAML плагина (не литералы RnA в train).
    isolation_forbid: tuple[IsolationForbidRule, ...] = ()
    required_phases: tuple[str, ...] = ()

    def head_id_for_phase(self, phase_id: str | None) -> str:
        if not phase_id:
            return self.default_head
        mapped = self.phase_to_head.get(str(phase_id))
        if mapped is None:
            warnings.warn(
                f"unknown phase_id={phase_id!r}; using default_head={self.default_head!r}",
                stacklevel=2,
            )
            return self.default_head
        if mapped not in self.heads:
            warnings.warn(
                f"phase_id={phase_id!r} maps to missing head_id={mapped!r}; "
                f"using default_head={self.default_head!r}",
                stacklevel=2,
            )
            return self.default_head
        return mapped

    def is_forbidden_pair(self, head_id: str, phase_id: str | None) -> bool:
        """True если YAML isolation.forbid запрещает эту пару head↔phase."""
        if not phase_id or not self.isolation_forbid:
            return False
        phase = str(phase_id)
        for rule in self.isolation_forbid:
            if head_id == rule.head and phase in rule.phases:
                return True
        return False

    def allowed_action_indices(
        self, head_id: str, action_strings: Sequence[str]
    ) -> list[int] | None:
        """Индексы разрешённых действий или None (все)."""
        if head_id not in self.action_masks:
            return None
        allowed = self.action_masks[head_id]
        if allowed is None:
            return None
        index = {str(a): i for i, a in enumerate(action_strings)}
        out: list[int] = []
        for name in allowed:
            if name not in index:
                raise ValueError(
                    f"action_masks[{head_id!r}] unknown action {name!r} "
                    f"not in action_strings={list(action_strings)}"
                )
            out.append(index[name])
        return out


def load_policy_heads_spec(game_id: str) -> PolicyHeadsSpec | None:
    """Прочитать policy_heads из games/<id>/env_config.yaml; None = обычный CnnPolicy."""
    path = game_dir(game_id) / "env_config.yaml"
    if not path.is_file():
        return None
    cfg = load_yaml(path)
    raw = cfg.get("policy_heads")
    if not raw:
        return None
    return parse_policy_heads_spec(raw)


def parse_policy_heads_spec(raw: dict[str, Any]) -> PolicyHeadsSpec:
    default_head = str(raw.get("default_head") or "").strip()
    if not default_head:
        raise ValueError("policy_heads.default_head is required")
    heads_raw = raw.get("heads") or []
    if not isinstance(heads_raw, (list, tuple)) or len(heads_raw) < 2:
        raise ValueError("policy_heads.heads must list ≥2 head ids")
    heads = tuple(str(h) for h in heads_raw)
    if default_head not in heads:
        raise ValueError(f"default_head={default_head!r} not in heads={heads}")
    phase_map_raw = raw.get("phase_to_head") or {}
    if not isinstance(phase_map_raw, dict):
        raise ValueError("policy_heads.phase_to_head must be a mapping")
    phase_to_head = {str(k): str(v) for k, v in phase_map_raw.items()}
    masks_raw = raw.get("action_masks") or {}
    if not isinstance(masks_raw, dict):
        raise ValueError("policy_heads.action_masks must be a mapping")
    action_masks: dict[str, tuple[str, ...] | None] = {}
    for hid, val in masks_raw.items():
        key = str(hid)
        if val is None:
            action_masks[key] = None
        elif isinstance(val, (list, tuple)):
            action_masks[key] = tuple(str(x) for x in val)
        else:
            raise ValueError(f"action_masks[{key!r}] must be list or null")

    isolation_forbid, required_phases = _parse_isolation(raw, heads)
    return PolicyHeadsSpec(
        default_head=default_head,
        heads=heads,
        phase_to_head=phase_to_head,
        action_masks=action_masks,
        isolation_forbid=isolation_forbid,
        required_phases=required_phases,
    )


def _parse_isolation(
    raw: dict[str, Any], heads: tuple[str, ...]
) -> tuple[tuple[IsolationForbidRule, ...], tuple[str, ...]]:
    iso = raw.get("isolation")
    if iso is None:
        return (), ()
    if not isinstance(iso, dict):
        raise ValueError("policy_heads.isolation must be a mapping")
    forbid_raw = iso.get("forbid") or []
    if not isinstance(forbid_raw, list):
        raise ValueError("policy_heads.isolation.forbid must be a list")
    rules: list[IsolationForbidRule] = []
    for i, item in enumerate(forbid_raw):
        if not isinstance(item, dict):
            raise ValueError(f"isolation.forbid[{i}] must be a mapping")
        head = str(item.get("head") or "").strip()
        phases_raw = item.get("phases") or []
        if not head:
            raise ValueError(f"isolation.forbid[{i}].head is required")
        if head not in heads:
            raise ValueError(
                f"isolation.forbid[{i}].head={head!r} not in heads={heads}"
            )
        if not isinstance(phases_raw, (list, tuple)) or not phases_raw:
            raise ValueError(f"isolation.forbid[{i}].phases must be a non-empty list")
        rules.append(
            IsolationForbidRule(head=head, phases=frozenset(str(p) for p in phases_raw))
        )
    required_raw = iso.get("required_phases") or []
    if not isinstance(required_raw, (list, tuple)):
        raise ValueError("policy_heads.isolation.required_phases must be a list")
    required = tuple(str(p) for p in required_raw)
    return tuple(rules), required


def evaluate_phase_head_gate(
    *,
    forbidden_steps: int,
    total_steps: int,
    phase_step_counts: dict[str, int],
    spec: PolicyHeadsSpec,
) -> tuple[bool, list[str]]:
    """Проверка isolation/required после learn. Возвращает (ok, сообщения об ошибках)."""
    errors: list[str] = []
    if spec.isolation_forbid and total_steps > 0 and forbidden_steps > 0:
        errors.append(
            f"phase-head isolation failed: forbidden head↔phase pairs "
            f"({forbidden_steps}/{total_steps})"
        )
    for phase in spec.required_phases:
        if total_steps > 0 and int(phase_step_counts.get(phase, 0)) <= 0:
            errors.append(
                f"phase-head coverage failed: never reached phase_id={phase!r}"
            )
    return (len(errors) == 0), errors


def load_game_action_strings(game_id: str) -> tuple[str, ...]:
    cfg = load_yaml(game_dir(game_id) / "env_config.yaml")
    actions = cfg.get("actions") or []
    return tuple(str(a) for a in actions)


def resolve_model_zip(mission: Path, model_arg: str | Path) -> Path:
    """Путь к models/genN.zip (один файл; без multi-zip каталога)."""
    raw = Path(model_arg)
    candidates: list[Path] = []
    if raw.is_absolute():
        candidates.append(raw)
    else:
        candidates.append(mission / raw)
        candidates.append(mission / "models" / raw)
    tried: list[str] = []
    for base in candidates:
        tried.append(str(base))
        zip_path = base if base.suffix.lower() == ".zip" else base.with_suffix(".zip")
        tried.append(str(zip_path))
        if zip_path.is_file():
            return zip_path.resolve()
        if base.is_file() and base.suffix.lower() == ".zip":
            return base.resolve()
    raise FileNotFoundError("Model zip not found. Tried: " + ", ".join(tried))


def predict_with_phase(
    model: PPO,
    obs: Any,
    phase_id: str | None,
    spec: PolicyHeadsSpec | None,
    *,
    deterministic: bool = True,
) -> tuple[Any, Any, str]:
    """predict + head_id; для обычного CnnPolicy head_id='default'."""
    if spec is None or not hasattr(model.policy, "set_active_head"):
        action, state = model.predict(obs, deterministic=deterministic)
        return action, state, "default"
    head_id = spec.head_id_for_phase(phase_id)
    model.policy.set_active_head(head_id)
    action, state = model.predict(obs, deterministic=deterministic)
    return action, state, head_id


def build_action_mask_table(
    spec: PolicyHeadsSpec, action_strings: Sequence[str]
) -> dict[str, np.ndarray]:
    """head_id → bool mask [n_actions] (True=allowed)."""
    n = len(action_strings)
    table: dict[str, np.ndarray] = {}
    for head_id in spec.heads:
        allowed = spec.allowed_action_indices(head_id, action_strings)
        if allowed is None:
            table[head_id] = np.ones(n, dtype=bool)
        else:
            m = np.zeros(n, dtype=bool)
            m[list(allowed)] = True
            if not m.any():
                raise ValueError(f"action mask for head {head_id!r} is empty")
            table[head_id] = m
    return table


def masks_to_torch(
    table: dict[str, np.ndarray], heads: Sequence[str], device: th.device
) -> dict[str, th.Tensor]:
    return {
        h: th.as_tensor(table[h], dtype=th.bool, device=device) for h in heads if h in table
    }
