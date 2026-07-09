"""Behavioral Cloning на demos/seg_*.npz (optional перед PPO)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import torch
import yaml
from stable_baselines3 import PPO
from stable_baselines3.common.policies import ActorCriticCnnPolicy

from project_paths import game_dir, load_yaml, mission_dir
from train.action_map import action_string_to_index


class _BcDataset(torch.utils.data.Dataset):
    def __init__(self, obs: np.ndarray, actions: np.ndarray) -> None:
        self.obs = torch.as_tensor(obs, dtype=torch.float32)
        self.actions = torch.as_tensor(actions, dtype=torch.long)

    def __len__(self) -> int:
        return int(self.actions.shape[0])

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        return self.obs[idx], self.actions[idx]


def _game_id_from_mission(mission: Path) -> str:
    parts = mission.parts
    idx = parts.index("games")
    return parts[idx + 1]


def _load_human_actions(mission: Path, frame_start: int, frame_end: int) -> list[int]:
    human_path = mission / "reference" / "human_playthrough.jsonl"
    cfg = load_yaml(game_dir(_game_id_from_mission(mission)) / "env_config.yaml")
    action_strings = tuple(cfg.get("actions") or [])
    by_frame: dict[int, str] = {}
    with human_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            by_frame[int(row["frame"])] = str(row.get("action", ""))

    actions: list[int] = []
    for frame in range(frame_start, frame_end + 1):
        row_action = by_frame.get(frame, "")
        actions.append(action_string_to_index(row_action, action_strings))
    return actions


def load_demo_dataset(
    mission: Path,
    *,
    demo_paths: list[Path] | None = None,
    require_real_obs: bool = True,
) -> tuple[np.ndarray, np.ndarray] | None:
    """Собирает (obs, actions) из npz; actions пересчитываются из human jsonl."""
    demos_dir = mission / "demos"
    paths = demo_paths or sorted(demos_dir.glob("seg_*.npz"))
    if not paths:
        return None

    manifest = yaml.safe_load((mission / "config" / "playthrough_manifest.yaml").read_text(encoding="utf-8")) or {}
    seg_by_id = {seg["id"]: seg for seg in manifest.get("segments") or []}

    obs_parts: list[np.ndarray] = []
    act_parts: list[np.ndarray] = []
    for path in paths:
        data = np.load(path, allow_pickle=True)
        meta_raw = data["meta"]
        meta: dict[str, Any] = json.loads(str(meta_raw.item() if hasattr(meta_raw, "item") else meta_raw))
        if require_real_obs and meta.get("obs_stub"):
            print(f"skip {path.name}: obs_stub (пересоберите demos с реальными obs)")
            continue

        seg_id = meta.get("segment_id") or path.stem
        seg = seg_by_id.get(seg_id, {})
        frame_start = int(meta.get("frame_start") or seg.get("frame_start", 0))
        frame_end = int(meta.get("frame_end") or seg.get("frame_end", 0))
        actions = _load_human_actions(mission, frame_start, frame_end)
        obs = np.asarray(data["obs"], dtype=np.float32)
        n = min(len(actions), obs.shape[0])
        if n == 0:
            continue
        obs_parts.append(obs[:n])
        act_parts.append(np.asarray(actions[:n], dtype=np.int64))

    if not obs_parts:
        return None
    return np.concatenate(obs_parts, axis=0), np.concatenate(act_parts, axis=0)


def bc_pretrain(
    model: PPO,
    mission: Path,
    *,
    demo_paths: list[Path] | None = None,
    epochs: int = 5,
    batch_size: int = 256,
    learning_rate: float = 1e-4,
) -> int:
    """Supervised BC на policy CNN. Возвращает число использованных transitions."""
    dataset = load_demo_dataset(mission, demo_paths=demo_paths, require_real_obs=True)
    if dataset is None:
        print("BC skipped: нет demos с реальными obs")
        return 0

    obs, actions = dataset
    loader = torch.utils.data.DataLoader(
        _BcDataset(obs, actions),
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
        for batch_obs, batch_act in loader:
            optimizer.zero_grad()
            features = policy.extract_features(batch_obs, policy.features_extractor)
            latent_pi = policy.mlp_extractor.forward_actor(features)
            logits = policy.action_net(latent_pi)
            loss = loss_fn(logits, batch_act)
            loss.backward()
            optimizer.step()
            epoch_loss += float(loss.item())
            batches += 1
            steps += int(batch_act.shape[0])
        avg = epoch_loss / max(batches, 1)
        print(f"BC epoch {epoch + 1}/{epochs} loss={avg:.4f} samples={len(obs)}")

    policy.set_training_mode(False)
    return steps


def resolve_demo_paths(mission: Path, demo_segment: str | None) -> list[Path] | None:
    if not demo_segment:
        return None
    path = Path(demo_segment)
    if not path.is_absolute():
        path = mission / path
    return [path]
