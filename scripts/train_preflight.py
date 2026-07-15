#!/usr/bin/env python3
"""Обязательная очистка перед train (вызывается из train_local.sh)."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from train.env_factory import require_clean_preflight  # noqa: E402


def main() -> None:
    require_clean_preflight(label="train_preflight")


if __name__ == "__main__":
    main()
