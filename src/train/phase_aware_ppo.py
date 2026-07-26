"""PPO с Multi-head: sync phase_id → head на collect и train."""
from __future__ import annotations

from typing import Any

import numpy as np
import torch as th
import torch.nn.functional as F
from gymnasium import spaces
from stable_baselines3 import PPO
from stable_baselines3.common.buffers import RolloutBuffer
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.utils import explained_variance
from stable_baselines3.common.vec_env import VecEnv

from train.phase_heads import PolicyHeadsSpec


class PhaseAwarePPO(PPO):
    """PPO + MultiHeadActorCriticPolicy: головы по phase_id из infos."""

    def __init__(
        self, *args: Any, heads_spec: PolicyHeadsSpec | None = None, **kwargs: Any
    ) -> None:
        self.heads_spec = heads_spec
        self._last_phase_ids: list[str | None] = []
        self._rollout_heads: np.ndarray | None = None
        self._heads_flat: np.ndarray | None = None
        self._isolation_counts = {"gameplay_on_title_intro": 0, "total_steps": 0}
        self._phase_step_counts: dict[str, int] = {}
        super().__init__(*args, **kwargs)

    def _phase_indices(self, phase_ids: list[str | None]) -> np.ndarray:
        if self.heads_spec is None:
            raise RuntimeError("PhaseAwarePPO.heads_spec is not set")
        idxs = []
        for p in phase_ids:
            hid = self.heads_spec.head_id_for_phase(p)
            idxs.append(self.heads_spec.heads.index(hid))
        return np.asarray(idxs, dtype=np.int64)

    def _read_phase_ids_from_infos(self, infos: list[dict] | tuple) -> list[str | None]:
        return [info.get("phase_id") if isinstance(info, dict) else None for info in infos]

    def _bootstrap_phase_ids(self, env: VecEnv) -> list[str | None]:
        reset_infos = getattr(env, "reset_infos", None)
        if reset_infos:
            return self._read_phase_ids_from_infos(reset_infos)
        return [None] * env.num_envs

    def collect_rollouts(
        self,
        env: VecEnv,
        callback: BaseCallback,
        rollout_buffer: RolloutBuffer,
        n_rollout_steps: int,
    ) -> bool:
        assert self._last_obs is not None
        self.policy.set_training_mode(False)
        n_steps = 0
        rollout_buffer.reset()
        self._heads_flat = None
        head_rows: list[np.ndarray] = []
        # isolation копит за всю сессию learn (не сбрасывать каждый rollout)

        if self.use_sde:
            self.policy.reset_noise(env.num_envs)

        callback.on_rollout_start()
        self._last_phase_ids = self._bootstrap_phase_ids(env)

        while n_steps < n_rollout_steps:
            if self.use_sde and self.sde_sample_freq > 0 and n_steps % self.sde_sample_freq == 0:
                self.policy.reset_noise(env.num_envs)

            phase_idxs = self._phase_indices(self._last_phase_ids)
            head_rows.append(phase_idxs.copy())
            for i, p in enumerate(self._last_phase_ids):
                self._isolation_counts["total_steps"] += 1
                phase_key = str(p) if p else "none"
                self._phase_step_counts[phase_key] = self._phase_step_counts.get(phase_key, 0) + 1
                hid = self.heads_spec.heads[int(phase_idxs[i])]
                if hid == "gameplay" and p in ("title", "intro"):
                    self._isolation_counts["gameplay_on_title_intro"] += 1

            with th.no_grad():
                from stable_baselines3.common.utils import obs_as_tensor

                obs_tensor = obs_as_tensor(self._last_obs, self.device)
                self.policy.set_batch_head_indices(phase_idxs)
                actions, values, log_probs = self.policy(obs_tensor)
            actions = actions.cpu().numpy()

            clipped_actions = actions
            if isinstance(self.action_space, spaces.Box):
                if self.policy.squash_output:
                    clipped_actions = self.policy.unscale_action(clipped_actions)
                else:
                    clipped_actions = np.clip(actions, self.action_space.low, self.action_space.high)

            new_obs, rewards, dones, infos = env.step(clipped_actions)
            self.num_timesteps += env.num_envs
            callback.update_locals(locals())
            if not callback.on_step():
                return False

            self._update_info_buffer(infos, dones)
            n_steps += 1

            if isinstance(self.action_space, spaces.Discrete):
                actions = actions.reshape(-1, 1)

            for idx, done in enumerate(dones):
                if (
                    done
                    and infos[idx].get("terminal_observation") is not None
                    and infos[idx].get("TimeLimit.truncated", False)
                ):
                    terminal_obs = self.policy.obs_to_tensor(infos[idx]["terminal_observation"])[0]
                    with th.no_grad():
                        terminal_value = self.policy.predict_values(terminal_obs)[0]
                    rewards[idx] += self.gamma * terminal_value

            rollout_buffer.add(
                self._last_obs,
                actions,
                rewards,
                self._last_episode_starts,
                values,
                log_probs,
            )
            self._last_obs = new_obs
            self._last_episode_starts = dones
            # phase_id на new_obs — для следующего решения
            self._last_phase_ids = self._read_phase_ids_from_infos(infos)
            for idx, done in enumerate(dones):
                if done:
                    # после auto-reset SB3 кладёт phase в infos / reset_infos
                    if "phase_id" not in infos[idx] and hasattr(env, "reset_infos"):
                        ri = env.reset_infos[idx] if idx < len(env.reset_infos) else {}
                        self._last_phase_ids[idx] = ri.get("phase_id") if isinstance(ri, dict) else None

        with th.no_grad():
            from stable_baselines3.common.utils import obs_as_tensor

            values = self.policy.predict_values(obs_as_tensor(new_obs, self.device))

        rollout_buffer.compute_returns_and_advantage(last_values=values, dones=dones)
        callback.update_locals(locals())
        callback.on_rollout_end()

        self._rollout_heads = np.stack(head_rows, axis=0)
        bad = self._isolation_counts["gameplay_on_title_intro"]
        total = max(self._isolation_counts["total_steps"], 1)
        self.logger.record("train/gameplay_head_on_title_intro_steps", bad)
        self.logger.record("train/phase_head_isolation_ok", float(bad == 0))
        self.logger.record("train/phase_head_steps", total)
        for phase_key, n in self._phase_step_counts.items():
            self.logger.record(f"train/phase_steps/{phase_key}", n)
        self.logger.record(
            "train/phase_reached_gameplay",
            float(self._phase_step_counts.get("gameplay", 0) > 0),
        )
        if hasattr(self.policy, "clear_batch_heads"):
            self.policy.clear_batch_heads()
        return True

    def train(self) -> None:
        assert self._rollout_heads is not None
        self.policy.set_training_mode(True)
        self._update_learning_rate(self.policy.optimizer)
        clip_range = self.clip_range(self._current_progress_remaining)  # type: ignore[operator]
        clip_range_vf = None
        if self.clip_range_vf is not None:
            clip_range_vf = self.clip_range_vf(self._current_progress_remaining)  # type: ignore[operator]

        # Тот же flatten, что RolloutBuffer.get
        heads_flat = RolloutBuffer.swap_and_flatten(
            self._rollout_heads.reshape(self._rollout_heads.shape[0], self._rollout_heads.shape[1], 1)
        ).astype(np.int64).reshape(-1)

        entropy_losses, pg_losses, value_losses, clip_fractions = [], [], [], []
        continue_training = True
        loss = th.tensor(0.0)

        for epoch in range(self.n_epochs):
            approx_kl_divs = []
            # Собственный shuffle с головами
            indices = np.random.permutation(self.rollout_buffer.buffer_size * self.rollout_buffer.n_envs)
            if not self.rollout_buffer.generator_ready:
                for tensor in (
                    "observations",
                    "actions",
                    "values",
                    "log_probs",
                    "advantages",
                    "returns",
                ):
                    self.rollout_buffer.__dict__[tensor] = self.rollout_buffer.swap_and_flatten(
                        self.rollout_buffer.__dict__[tensor]
                    )
                self.rollout_buffer.generator_ready = True

            batch_size = self.batch_size
            start_idx = 0
            n_total = self.rollout_buffer.buffer_size * self.rollout_buffer.n_envs
            while start_idx < n_total:
                batch_inds = indices[start_idx : start_idx + batch_size]
                start_idx += batch_size
                rollout_data = self.rollout_buffer._get_samples(batch_inds)
                self.policy.set_batch_head_indices(heads_flat[batch_inds])

                actions = rollout_data.actions
                if isinstance(self.action_space, spaces.Discrete):
                    actions = rollout_data.actions.long().flatten()

                values, log_prob, entropy = self.policy.evaluate_actions(
                    rollout_data.observations, actions
                )
                values = values.flatten()
                advantages = rollout_data.advantages
                if self.normalize_advantage and len(advantages) > 1:
                    advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

                ratio = th.exp(log_prob - rollout_data.old_log_prob)
                policy_loss_1 = advantages * ratio
                policy_loss_2 = advantages * th.clamp(ratio, 1 - clip_range, 1 + clip_range)
                policy_loss = -th.min(policy_loss_1, policy_loss_2).mean()
                pg_losses.append(policy_loss.item())
                clip_fractions.append(th.mean((th.abs(ratio - 1) > clip_range).float()).item())

                if clip_range_vf is None:
                    values_pred = values
                else:
                    values_pred = rollout_data.old_values + th.clamp(
                        values - rollout_data.old_values, -clip_range_vf, clip_range_vf
                    )
                value_loss = F.mse_loss(rollout_data.returns, values_pred)
                value_losses.append(value_loss.item())

                if entropy is None:
                    entropy_loss = -th.mean(-log_prob)
                else:
                    entropy_loss = -th.mean(entropy)
                entropy_losses.append(entropy_loss.item())

                loss = policy_loss + self.ent_coef * entropy_loss + self.vf_coef * value_loss
                with th.no_grad():
                    log_ratio = log_prob - rollout_data.old_log_prob
                    approx_kl_div = th.mean((th.exp(log_ratio) - 1) - log_ratio).cpu().numpy()
                    approx_kl_divs.append(approx_kl_div)

                if self.target_kl is not None and approx_kl_div > 1.5 * self.target_kl:
                    continue_training = False
                    break

                self.policy.optimizer.zero_grad()
                loss.backward()
                th.nn.utils.clip_grad_norm_(self.policy.parameters(), self.max_grad_norm)
                self.policy.optimizer.step()

            self._n_updates += 1
            if not continue_training:
                break

        explained_var = explained_variance(
            self.rollout_buffer.values.flatten(), self.rollout_buffer.returns.flatten()
        )
        self.logger.record("train/entropy_loss", np.mean(entropy_losses))
        self.logger.record("train/policy_gradient_loss", np.mean(pg_losses))
        self.logger.record("train/value_loss", np.mean(value_losses))
        self.logger.record("train/approx_kl", np.mean(approx_kl_divs) if approx_kl_divs else 0.0)
        self.logger.record("train/clip_fraction", np.mean(clip_fractions) if clip_fractions else 0.0)
        self.logger.record("train/loss", float(loss.item()))
        self.logger.record("train/explained_variance", explained_var)
        self.logger.record("train/n_updates", self._n_updates, exclude="tensorboard")
        self.logger.record("train/clip_range", clip_range)
        if hasattr(self.policy, "clear_batch_heads"):
            self.policy.clear_batch_heads()
