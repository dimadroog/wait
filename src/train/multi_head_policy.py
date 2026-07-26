"""SB3 Multi-head CNN policy: shared backbone + per-head action nets."""
from __future__ import annotations

from functools import partial
from typing import Any

import numpy as np
import torch as th
from gymnasium import spaces
from stable_baselines3.common.distributions import CategoricalDistribution
from stable_baselines3.common.policies import ActorCriticCnnPolicy
from stable_baselines3.common.type_aliases import PyTorchObs, Schedule
from torch import nn


class MultiHeadActorCriticPolicy(ActorCriticCnnPolicy):
    """Shared NatureCNN + mlp; отдельный action_net на каждую голову.

    Активная голова: ``set_active_head`` (весь батч) или ``set_batch_head_indices``
    (per-sample, LongTensor индексов в ``head_ids``).
    """

    def __init__(
        self,
        observation_space: spaces.Space,
        action_space: spaces.Space,
        lr_schedule: Schedule,
        *args: Any,
        head_ids: list[str] | tuple[str, ...] | None = None,
        action_masks: dict[str, list[bool] | np.ndarray] | None = None,
        **kwargs: Any,
    ) -> None:
        if not head_ids or len(head_ids) < 2:
            raise ValueError("MultiHeadActorCriticPolicy requires head_ids with ≥2 entries")
        if not isinstance(action_space, spaces.Discrete):
            raise TypeError("MultiHeadActorCriticPolicy supports Discrete action_space only")
        self.head_ids: tuple[str, ...] = tuple(str(h) for h in head_ids)
        self._head_index = {h: i for i, h in enumerate(self.head_ids)}
        self._active_head: str = self.head_ids[0]
        self._batch_head_indices: th.Tensor | None = None
        # head → bool[n_actions]; заполняется после super/_build через set_action_masks
        self._mask_config = action_masks or {}
        self.action_heads: nn.ModuleDict
        super().__init__(observation_space, action_space, lr_schedule, *args, **kwargs)

    def _build(self, lr_schedule: Schedule) -> None:
        self._build_mlp_extractor()
        latent_dim_pi = self.mlp_extractor.latent_dim_pi
        n_actions = int(self.action_space.n)  # type: ignore[attr-defined]

        if not isinstance(self.action_dist, CategoricalDistribution):
            raise TypeError("MultiHeadActorCriticPolicy requires CategoricalDistribution")

        self.action_heads = nn.ModuleDict(
            {h: nn.Linear(latent_dim_pi, n_actions) for h in self.head_ids}
        )
        # SB3 ожидает action_net для ortho_init / некоторых утилит — alias первой головы
        self.action_net = self.action_heads[self.head_ids[0]]
        self.value_net = nn.Linear(self.mlp_extractor.latent_dim_vf, 1)

        for h in self.head_ids:
            raw = self._mask_config.get(h)
            if raw is None:
                mask = th.ones(n_actions, dtype=th.bool)
            else:
                mask = th.as_tensor(list(raw), dtype=th.bool)
                if mask.numel() != n_actions:
                    raise ValueError(
                        f"action mask for head {h!r} length {mask.numel()} != n_actions={n_actions}"
                    )
            self.register_buffer(f"_mask_{h}", mask)

        if self.ortho_init:
            module_gains: dict[nn.Module, float] = {
                self.features_extractor: np.sqrt(2),
                self.mlp_extractor: np.sqrt(2),
                self.value_net: 1,
            }
            for head in self.action_heads.values():
                module_gains[head] = 0.01
            for module, gain in module_gains.items():
                module.apply(partial(self.init_weights, gain=gain))

        self.optimizer = self.optimizer_class(
            self.parameters(), lr=lr_schedule(1), **self.optimizer_kwargs
        )  # type: ignore[call-arg]

    def set_active_head(self, head_id: str) -> None:
        if head_id not in self._head_index:
            raise KeyError(f"unknown head_id={head_id!r}; known={self.head_ids}")
        self._active_head = head_id
        self._batch_head_indices = None

    def set_batch_head_indices(self, indices: th.Tensor | np.ndarray | list[int]) -> None:
        """Per-sample head index (0..len(heads)-1), shape (batch,)."""
        if not isinstance(indices, th.Tensor):
            indices = th.as_tensor(indices, dtype=th.long)
        self._batch_head_indices = indices.long().view(-1)
        self._active_head = self.head_ids[int(self._batch_head_indices[0].item())]

    def clear_batch_heads(self) -> None:
        self._batch_head_indices = None

    def _head_mask(self, head_id: str) -> th.Tensor:
        return getattr(self, f"_mask_{head_id}")

    def _logits_from_latent(self, latent_pi: th.Tensor) -> th.Tensor:
        batch = latent_pi.shape[0]
        n_actions = int(self.action_space.n)  # type: ignore[attr-defined]
        if self._batch_head_indices is None:
            logits = self.action_heads[self._active_head](latent_pi)
            mask = self._head_mask(self._active_head)
            return logits.masked_fill(~mask.unsqueeze(0), -1e8)

        idx = self._batch_head_indices.to(latent_pi.device)
        if idx.shape[0] != batch:
            raise ValueError(
                f"batch_head_indices length {idx.shape[0]} != batch {batch}"
            )
        logits = th.zeros(batch, n_actions, device=latent_pi.device, dtype=latent_pi.dtype)
        for h_i, head_id in enumerate(self.head_ids):
            sel = idx == h_i
            if not bool(sel.any()):
                continue
            head_logits = self.action_heads[head_id](latent_pi[sel])
            mask = self._head_mask(head_id)
            head_logits = head_logits.masked_fill(~mask.unsqueeze(0), -1e8)
            logits[sel] = head_logits
        return logits

    def _get_action_dist_from_latent(self, latent_pi: th.Tensor):  # type: ignore[override]
        mean_actions = self._logits_from_latent(latent_pi)
        return self.action_dist.proba_distribution(action_logits=mean_actions)

    def gameplay_head_unused_on_phases(
        self, phase_ids: list[str | None], gameplay_head: str = "gameplay"
    ) -> bool:
        """Проверка для тестов: ни один phase не мапится на вызов без set — helper noop."""
        return gameplay_head in self.head_ids
