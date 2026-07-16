"""Unit tests for FM2 playback argv."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fm2_playback import fceux_playmovie_argv  # noqa: E402


def test_fceux_playmovie_argv_embed_readonly(tmp_path: Path) -> None:
    fm2 = tmp_path / "playback.fm2"
    rom = tmp_path / "rushn_attack"
    fm2.write_text("x\n", encoding="utf-8")
    rom.write_text("x\n", encoding="utf-8")
    argv = fceux_playmovie_argv(staged_fm2=fm2, staged_rom=rom)
    assert argv == [
        "-playmovie",
        "playback.fm2",
        "-readonly",
        "1",
        "rushn_attack",
    ]
