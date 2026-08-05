#!/usr/bin/env python3
"""Операторский GUI-лаунчер: Config / Inference / Train."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from operator_launcher.app import main  # noqa: E402

if __name__ == "__main__":
    main()
