"""Сопоставление строк действий FM2/эталона с индексами env."""
from __future__ import annotations

from typing import Sequence


def _buttons(action: str) -> frozenset[str]:
    s = (action or "").strip()
    if not s:
        return frozenset()
    return frozenset(s.split("+"))


def action_string_to_index(action: str, action_strings: Sequence[str]) -> int:
    """Ближайшее действие из env_config.actions."""
    want = _buttons(action)
    for i, candidate in enumerate(action_strings):
        if _buttons(candidate) == want:
            return i

    best_i = 0
    best_score = -1
    for i, candidate in enumerate(action_strings):
        have = _buttons(candidate)
        score = len(want & have)
        if score > best_score:
            best_score = score
            best_i = i
    return best_i
