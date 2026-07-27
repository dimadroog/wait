"""G8 волна B: логика ram_scout в src/ (без FCEUX)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from project_paths import repo_root
from ram_scout import prepare_scout_paths, stage_fm2, write_candidates_only


def test_prepare_scout_paths_shell_vs_mission(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ram_scout.repo_root", lambda: tmp_path)
    monkeypatch.setattr("ram_scout.game_scout_dir", lambda gid, rid: tmp_path / "games" / gid / "reference" / "scout" / rid)
    monkeypatch.setattr(
        "ram_scout.game_ram_scout_jsonl_path",
        lambda gid, rid: tmp_path / "games" / gid / "reference" / "scout" / rid / "ram_scout.jsonl",
    )
    monkeypatch.setattr(
        "ram_scout.game_ram_scout_candidates_path",
        lambda gid, rid: tmp_path / "games" / gid / "reference" / "scout" / rid / "ram_scout_candidates.json",
    )

    shell = prepare_scout_paths(
        game_id="demo",
        scope="shell",
        mission=None,
        round_id="title",
        write_ram_map=True,  # shell ignores write_ram_map
    )
    assert shell.do_resolve is False
    assert "scout" in shell.jsonl.parts and "title" in shell.jsonl.parts

    mission = tmp_path / "games" / "demo" / "missions" / "m1"
    (mission / "config").mkdir(parents=True)
    (mission / "reference" / "scout").mkdir(parents=True)
    monkeypatch.setattr("ram_scout.mission_scout_dir", lambda m: m / "reference" / "scout")
    monkeypatch.setattr("ram_scout.ram_scout_jsonl_path", lambda m: m / "reference" / "scout" / "ram_scout.jsonl")
    monkeypatch.setattr(
        "ram_scout.ram_scout_candidates_path",
        lambda m: m / "reference" / "scout" / "ram_scout_candidates.json",
    )
    monkeypatch.setattr("ram_scout.ram_resolve_path", lambda m: m / "config" / "ram_resolve.json")

    miss = prepare_scout_paths(
        game_id="demo",
        scope="mission",
        mission=mission,
        round_id="clear",
        write_ram_map=False,
    )
    assert miss.do_resolve is False
    assert miss.jsonl == mission / "reference" / "scout" / "ram_scout.jsonl"

    miss_write = prepare_scout_paths(
        game_id="demo",
        scope="mission",
        mission=mission,
        round_id="clear",
        write_ram_map=True,
    )
    assert miss_write.do_resolve is True


def test_stage_fm2_copies_rom_aliases(tmp_path: Path) -> None:
    fm2 = tmp_path / "clear.fm2"
    fm2.write_text('romFilename foo.nes\n|0|........||\n', encoding="utf-8")
    rom = tmp_path / "real.nes"
    rom.write_bytes(b"NES\x1a" + b"\x00" * 16)
    staging = tmp_path / "staging"
    staged_fm2, staged_rom = stage_fm2(fm2, rom, staging)
    assert staged_fm2.is_file()
    assert staged_rom.name == "foo.nes"
    assert (staging / "foo.nes").is_file()
    assert (staging / "foo.nes.nes").is_file()
    assert (staging / "real.nes").is_file()


def test_write_candidates_only(tmp_path: Path) -> None:
    jsonl = tmp_path / "ram_scout.jsonl"
    ram = "00" * 2048
    rows = [
        {"frame": 0, "input": "", "ram_hex": ram},
        {"frame": 1, "input": "right", "ram_hex": "01" + "00" * 2047},
    ]
    jsonl.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    out = tmp_path / "candidates.json"
    write_candidates_only(jsonl, out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["frame_count"] == 2
    assert "candidates" in payload


def test_src_ram_scout_module_importable() -> None:
    import ram_scout as mod

    assert (repo_root() / "src" / "ram_scout.py").is_file()
    assert callable(mod.run_ram_scout)
