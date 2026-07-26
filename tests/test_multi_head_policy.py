"""Unit: MultiHeadActorCriticPolicy head select + action mask."""
from __future__ import annotations

import numpy as np
import torch as th
from gymnasium import spaces
from train.multi_head_policy import MultiHeadActorCriticPolicy
from train.phase_heads import parse_policy_heads_spec, predict_with_phase


def _make_policy() -> MultiHeadActorCriticPolicy:
    obs_space = spaces.Box(0, 1, shape=(4, 84, 84), dtype=np.float32)
    act_space = spaces.Discrete(4)  # "", left, right, start
    masks = {
        "intro": [True, False, False, True],
        "gameplay": [True, True, True, True],
    }
    policy = MultiHeadActorCriticPolicy(
        obs_space,
        act_space,
        lambda _progress: 3e-4,
        head_ids=["intro", "gameplay"],
        action_masks=masks,
        normalize_images=False,
    )
    policy.set_training_mode(False)
    return policy


def test_intro_mask_blocks_non_start_actions() -> None:
    policy = _make_policy()
    policy.set_active_head("intro")
    obs = th.zeros((8, 4, 84, 84), dtype=th.float32)
    with th.no_grad():
        actions, _values, _logp = policy(obs, deterministic=True)
    actions_np = actions.cpu().numpy().reshape(-1)
    # only indices 0 or 3 allowed
    assert set(actions_np.tolist()).issubset({0, 3})


def test_gameplay_head_can_use_all_actions() -> None:
    policy = _make_policy()
    policy.set_active_head("gameplay")
    obs = th.zeros((1, 4, 84, 84), dtype=th.float32)
    with th.no_grad():
        dist = policy.get_distribution(obs)
        logits = dist.distribution.logits
    assert logits.shape[-1] == 4
    # no -1e8 on gameplay
    assert bool(th.isfinite(logits).all())


def test_batch_heads_per_sample() -> None:
    policy = _make_policy()
    obs = th.zeros((4, 4, 84, 84), dtype=th.float32)
    # 0=intro, 1=gameplay
    policy.set_batch_head_indices([0, 0, 1, 1])
    with th.no_grad():
        actions, _, _ = policy(obs, deterministic=True)
    a = actions.cpu().numpy().reshape(-1)
    assert set(a[:2].tolist()).issubset({0, 3})


def test_predict_with_phase_selects_intro() -> None:
    """Smoke: predict_with_phase на mock PPO с MultiHead policy."""
    from unittest.mock import MagicMock

    policy = _make_policy()
    model = MagicMock()
    model.policy = policy
    model.predict = lambda obs, deterministic=True: (
        np.array([0]),
        None,
    )
    # real path sets head then calls model.predict
    spec = parse_policy_heads_spec(
        {
            "default_head": "gameplay",
            "heads": ["intro", "gameplay"],
            "phase_to_head": {"title": "intro", "gameplay": "gameplay"},
        }
    )

    def fake_predict(obs, deterministic=True):
        assert policy._active_head == "intro"
        return np.array([0]), None

    model.predict = fake_predict
    _action, _state, head_id = predict_with_phase(
        model, np.zeros((4, 84, 84), np.float32), "title", spec, deterministic=True
    )
    assert head_id == "intro"
