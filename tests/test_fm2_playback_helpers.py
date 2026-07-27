"""G8 волна C: общие FM2 playback helpers без FCEUX."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from fm2_playback import (
    fceux_playmovie_argv,
    reset_staging_dir,
    resolve_mission_relative_path,
    stage_rom,
    wait_fceux_process,
)


def test_stage_rom_aliases(tmp_path: Path) -> None:
    rom = tmp_path / "real.nes"
    rom.write_bytes(b"NES\x1a" + b"\x00" * 8)
    staging = tmp_path / "staging"
    staging.mkdir()
    staged = stage_rom(rom, staging, "foo.nes")
    assert staged.name == "foo.nes"
    assert (staging / "foo.nes").is_file()
    assert (staging / "foo.nes.nes").is_file()
    assert (staging / "real.nes").is_file()


def test_reset_staging_dir_clears(tmp_path: Path) -> None:
    staging = tmp_path / "st"
    staging.mkdir()
    (staging / "old.txt").write_text("x", encoding="utf-8")
    out = reset_staging_dir(staging)
    assert out == staging
    assert staging.is_dir()
    assert not (staging / "old.txt").exists()


def test_fceux_playmovie_argv() -> None:
    argv = fceux_playmovie_argv(
        staged_fm2=Path("a.fm2"),
        staged_rom=Path("rom.nes"),
    )
    assert argv == ["-playmovie", "a.fm2", "-readonly", "1", "rom.nes"]


def test_resolve_mission_relative_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mission = tmp_path / "m1"
    (mission / "logs").mkdir(parents=True)
    target = mission / "logs" / "playlist.json"
    target.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("fm2_playback.mission_dir", lambda g, m: mission)
    got = resolve_mission_relative_path(Path("logs/playlist.json"), "g", "m1")
    assert got == target.resolve()


def test_wait_fceux_done_flag(tmp_path: Path) -> None:
    done = tmp_path / "done.flag"
    proc = MagicMock()
    proc.returncode = 0
    proc.terminate = MagicMock()
    proc.wait = MagicMock(return_value=0)
    calls = {"n": 0}

    def poll_with_done() -> int | None:
        calls["n"] += 1
        if calls["n"] == 2:
            done.write_text("1", encoding="utf-8")
        # после done.flag процесс ещё жив → terminate
        if calls["n"] >= 4:
            return 0
        return None

    proc.poll = poll_with_done
    wait_fceux_process(proc, done_flag=done, timeout=5.0)
    proc.terminate.assert_called()
    proc.wait.assert_called()


def test_wait_fceux_timeout() -> None:
    proc = MagicMock()
    proc.poll = MagicMock(return_value=None)
    proc.terminate = MagicMock()
    with pytest.raises(TimeoutError, match="timeout"):
        wait_fceux_process(proc, done_flag=None, timeout=0.01)


def test_play_input_rejects_unknown(tmp_path: Path) -> None:
    from stream.play_fm2 import play_input

    bad = tmp_path / "notes.txt"
    bad.write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit, match="Expected"):
        play_input(bad, game="g", mission="m")
