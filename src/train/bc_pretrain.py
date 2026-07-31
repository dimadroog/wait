"""Behavioral Cloning на reference/demos_for_bc/seg_*.npz (optional перед PPO)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
import yaml
from stable_baselines3 import PPO
from stable_baselines3.common.policies import ActorCriticCnnPolicy

from demo_quality import validate_demo_npz
from playthrough_build import gameplay_start_frame_from_head_saves, load_head_save_states, nearest_head_save_rel
from project_paths import demos_for_bc_dir, mission_dir
from train.multi_head_policy import MultiHeadActorCriticPolicy
from train.phase_heads import PolicyHeadsSpec


@dataclass(frozen=True)
class _BcDemoBatch:
    obs: np.ndarray
    actions: np.ndarray
    head_indices: np.ndarray | None


class _BcDataset(torch.utils.data.Dataset):
    def __init__(
        self,
        obs: np.ndarray,
        actions: np.ndarray,
        head_indices: np.ndarray | None = None,
    ) -> None:
        self.obs = torch.as_tensor(obs, dtype=torch.float32)
        self.actions = torch.as_tensor(actions, dtype=torch.long)
        self.head_indices = (
            torch.as_tensor(head_indices, dtype=torch.long) if head_indices is not None else None
        )

    def __len__(self) -> int:
        return int(self.actions.shape[0])

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, ...]:
        if self.head_indices is None:
            return self.obs[idx], self.actions[idx]
        return self.obs[idx], self.actions[idx], self.head_indices[idx]


def checkpoint_id_from_save_rel(save_rel: str) -> str:
    """``save_states/cp_gameplay0.fc0`` → ``cp_gameplay0``."""
    name = Path(save_rel).name
    if name.endswith(".fc0"):
        return name[: -len(".fc0")]
    return Path(save_rel).stem


def checkpoint_id_to_head_map(head_save_states: dict[str, list[dict]] | None) -> dict[str, str]:
    if not head_save_states:
        return {}
    out: dict[str, str] = {}
    for head_id, items in head_save_states.items():
        for item in items:
            cp_id = str(item.get("id") or "")
            if cp_id:
                out[cp_id] = str(head_id)
    return out


def resolve_bc_head_id(
    seg: dict[str, Any],
    *,
    head_save_states: dict[str, list[dict]] | None,
    heads_spec: PolicyHeadsSpec,
) -> str:
    """Голова BC для сегмента манифеста (без литералов игры в вызывающем коде)."""
    explicit = seg.get("bc_head")
    if explicit is not None:
        head_id = str(explicit).strip()
        if head_id not in heads_spec.heads:
            raise ValueError(
                f"segment {seg.get('id')!r} bc_head={head_id!r} not in policy_heads.heads"
            )
        return head_id

    save_rel = seg.get("save_state")
    if not save_rel and head_save_states:
        save_rel = nearest_head_save_rel(int(seg.get("frame_start", 0)), head_save_states)
    cp_map = checkpoint_id_to_head_map(head_save_states)
    if save_rel:
        cp_id = checkpoint_id_from_save_rel(str(save_rel))
        mapped = cp_map.get(cp_id)
        if mapped and mapped in heads_spec.heads:
            return mapped

    return heads_spec.default_head


def load_demo_dataset(
    mission: Path,
    *,
    demo_paths: list[Path] | None = None,
    require_quality_pass: bool = True,
    heads_spec: PolicyHeadsSpec | None = None,
) -> _BcDemoBatch | None:
    """Собирает демо из npz; obs и actions — только из файла сегмента."""
    demos_dir = demos_for_bc_dir(mission)
    paths = demo_paths or sorted(demos_dir.glob("seg_*.npz"))
    if not paths:
        return None

    manifest_path = mission / "config" / "playthrough_manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    seg_by_id = {seg["id"]: seg for seg in manifest.get("segments") or []}
    head_save_states = load_head_save_states(mission)
    gameplay_start = gameplay_start_frame_from_head_saves(head_save_states)
    train_block = manifest.get("train") or {}
    if gameplay_start is None and train_block.get("gameplay_start_frame") is not None:
        gameplay_start = int(train_block["gameplay_start_frame"])

    obs_parts: list[np.ndarray] = []
    act_parts: list[np.ndarray] = []
    head_parts: list[np.ndarray] = []
    use_heads = heads_spec is not None
    head_index: dict[str, int] | None = None
    if use_heads and heads_spec is not None:
        head_index = {h: i for i, h in enumerate(heads_spec.heads)}

    for path in paths:
        quality = validate_demo_npz(path, gameplay_start_frame=gameplay_start)
        if require_quality_pass and not quality.passed:
            reasons = "; ".join(quality.failure_reasons())
            print(f"skip {path.name}: quality gate failed ({reasons})")
            continue

        with np.load(path, allow_pickle=True) as segment_npz:
            meta_raw = segment_npz["meta"]
            segment_meta: dict[str, Any] = json.loads(
                str(meta_raw.item() if hasattr(meta_raw, "item") else meta_raw)
            )
            obs = np.asarray(segment_npz["obs"], dtype=np.float32)
            actions = np.asarray(segment_npz["actions"], dtype=np.int64)

        n = min(int(obs.shape[0]), int(actions.shape[0]))
        if n == 0:
            continue
        if obs.shape[0] != actions.shape[0]:
            print(
                f"warning {path.name}: obs/actions length mismatch "
                f"({obs.shape[0]} vs {actions.shape[0]}), using n={n}"
            )

        seg_id = segment_meta.get("segment_id") or path.stem
        seg = seg_by_id.get(seg_id, {})
        obs_parts.append(obs[:n])
        act_parts.append(actions[:n])
        if use_heads and heads_spec is not None and head_index is not None:
            head_id = resolve_bc_head_id(
                {**seg, "id": seg_id},
                head_save_states=head_save_states,
                heads_spec=heads_spec,
            )
            print(f"BC segment {seg_id}: head={head_id} transitions={n}")
            head_parts.append(np.full(n, head_index[head_id], dtype=np.int64))

    if not obs_parts:
        return None
    head_arr = np.concatenate(head_parts, axis=0) if head_parts else None
    return _BcDemoBatch(
        obs=np.concatenate(obs_parts, axis=0),
        actions=np.concatenate(act_parts, axis=0),
        head_indices=head_arr,
    )


def _bc_logits(
    policy: ActorCriticCnnPolicy,
    batch_obs: torch.Tensor,
    batch_heads: torch.Tensor | None,
) -> torch.Tensor:
    features = policy.extract_features(batch_obs, policy.features_extractor)
    latent_pi = policy.mlp_extractor.forward_actor(features)
    if isinstance(policy, MultiHeadActorCriticPolicy) and batch_heads is not None:
        policy.set_batch_head_indices(batch_heads)
        return policy._logits_from_latent(latent_pi)
    return policy.action_net(latent_pi)


def bc_pretrain(
    model: PPO,
    mission: Path,
    *,
    demo_paths: list[Path] | None = None,
    epochs: int = 5,
    batch_size: int = 256,
    learning_rate: float = 1e-4,
    heads_spec: PolicyHeadsSpec | None = None,
) -> int:
    """Supervised BC на policy CNN / multi-head. Возвращает число transitions."""
    multi = isinstance(model.policy, MultiHeadActorCriticPolicy)
    if multi and heads_spec is None:
        print("BC skipped: multi-head policy but no policy_heads spec")
        return 0

    batch = load_demo_dataset(
        mission,
        demo_paths=demo_paths,
        require_quality_pass=True,
        heads_spec=heads_spec if multi else None,
    )
    if batch is None:
        print("BC skipped: нет demos, прошедших quality gate")
        return 0

    loader = torch.utils.data.DataLoader(
        _BcDataset(batch.obs, batch.actions, batch.head_indices),
        batch_size=batch_size,
        shuffle=True,
        drop_last=False,
    )
    policy = model.policy
    assert isinstance(policy, ActorCriticCnnPolicy)
    optimizer = torch.optim.Adam(policy.parameters(), lr=learning_rate)
    loss_fn = torch.nn.CrossEntropyLoss()

    policy.set_training_mode(True)
    steps = 0
    for epoch in range(epochs):
        epoch_loss = 0.0
        batches = 0
        for batch_item in loader:
            if len(batch_item) == 3:
                batch_obs, batch_act, batch_heads = batch_item
            else:
                batch_obs, batch_act = batch_item
                batch_heads = None
            optimizer.zero_grad()
            logits = _bc_logits(policy, batch_obs, batch_heads)
            loss = loss_fn(logits, batch_act)
            loss.backward()
            optimizer.step()
            epoch_loss += float(loss.item())
            batches += 1
            steps += int(batch_act.shape[0])
        avg = epoch_loss / max(batches, 1)
        mode = "multi-head" if batch.head_indices is not None else "single-head"
        print(
            f"BC epoch {epoch + 1}/{epochs} loss={avg:.4f} "
            f"samples={len(batch.actions)} ({mode})"
        )

    if isinstance(policy, MultiHeadActorCriticPolicy):
        policy.clear_batch_heads()
    policy.set_training_mode(False)
    return steps


def bc_demo_action_match_rate(
    model: PPO,
    mission: Path,
    *,
    heads_spec: PolicyHeadsSpec | None = None,
    demo_paths: list[Path] | None = None,
    batch_size: int = 256,
) -> tuple[int, int]:
    """Совпадение argmax политики с метками демо (offline, без env)."""
    multi = isinstance(model.policy, MultiHeadActorCriticPolicy)
    batch = load_demo_dataset(
        mission,
        demo_paths=demo_paths,
        require_quality_pass=True,
        heads_spec=heads_spec if multi else None,
    )
    if batch is None:
        return 0, 0
    policy = model.policy
    assert isinstance(policy, ActorCriticCnnPolicy)
    policy.set_training_mode(False)
    correct = 0
    n = int(batch.actions.shape[0])
    with torch.no_grad():
        for start in range(0, n, batch_size):
            end = min(start + batch_size, n)
            obs_t = torch.as_tensor(batch.obs[start:end], dtype=torch.float32)
            act_t = torch.as_tensor(batch.actions[start:end], dtype=torch.long)
            head_t = None
            if batch.head_indices is not None:
                head_t = torch.as_tensor(batch.head_indices[start:end], dtype=torch.long)
            logits = _bc_logits(policy, obs_t, head_t)
            pred = logits.argmax(dim=-1)
            correct += int((pred == act_t).sum().item())
    if isinstance(policy, MultiHeadActorCriticPolicy):
        policy.clear_batch_heads()
    return correct, n


def resolve_demo_paths(mission: Path, demo_segment: str | None) -> list[Path] | None:
    if not demo_segment:
        return None
    path = Path(demo_segment)
    if not path.is_absolute():
        path = mission / path
    return [path]
