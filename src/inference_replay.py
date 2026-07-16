"""Emulation replay inference_inputs.jsonl (BACKLOG 3.4)."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from fceux_launch import fceux_frame_skip, run_fceux_lua
from inference_states import resolve_inference_reset_state
from jsonl_logs import iter_jsonl
from project_paths import mission_dir, repo_root, resolve_rom

DEFAULT_FRAME_SKIP = 4
PROBE_RESET_FRAME = 1
PROBE_EPISODE_GAMEPLAY_FRAME = 200


def episode_step_actions(
    jsonl_path: Path,
    episode: int,
    *,
    frame_skip: int = DEFAULT_FRAME_SKIP,
) -> list[str]:
    """Плоский список action-строк (frame_skip кадров на env step)."""
    rows = [r for r in iter_jsonl(jsonl_path) if int(r.get("episode", -1)) == int(episode)]
    if not rows:
        raise ValueError(f"No rows for episode {episode} in {jsonl_path}")
    out: list[str] = []
    for row in rows:
        action = str(row.get("action", ""))
        for _ in range(frame_skip):
            out.append(action)
    return out


def episode_action_digest(
    jsonl_path: Path,
    episode: int,
    *,
    frame_skip: int = DEFAULT_FRAME_SKIP,
) -> str:
    digest = hashlib.md5()
    for action in episode_step_actions(jsonl_path, episode, frame_skip=frame_skip):
        digest.update(action.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def replay_frame_count(
    jsonl_path: Path,
    episode: int,
    *,
    frame_skip: int = DEFAULT_FRAME_SKIP,
) -> int:
    return len(episode_step_actions(jsonl_path, episode, frame_skip=frame_skip))


def stage_playback(
    *,
    game: str,
    mission: str,
    staging: Path,
    jsonl_path: Path,
) -> tuple[Path, Path, Path, Path]:
    """ROM + inference_cp0 + jsonl в staging; возвращает (rom, state, jsonl, staging)."""
    staging.mkdir(parents=True, exist_ok=True)
    mission_root = mission_dir(game, mission)
    rel_state = resolve_inference_reset_state(mission_root)
    state_src = mission_root / rel_state
    if not state_src.is_file():
        raise FileNotFoundError(f"Inference save state not found: {state_src}")

    rom_src = resolve_rom(game)
    staged_rom = staging / rom_src.name
    shutil.copy2(rom_src, staged_rom)
    for alt in (rom_src.stem, rom_src.stem + ".nes"):
        shutil.copy2(rom_src, staging / alt)

    staged_state = staging / state_src.name
    shutil.copy2(state_src, staged_state)
    staged_jsonl = staging / jsonl_path.name
    shutil.copy2(jsonl_path, staged_jsonl)
    return staged_rom, staged_state, staged_jsonl, staging


def run_inference_playback(
    *,
    jsonl_path: Path,
    episode: int,
    staging: Path,
    tmp_dir: Path,
    overlay_path: Path | None = None,
    frame_skip: int | None = None,
    timeout_sec: float = 120.0,
    turbo: bool = False,
    game: str = "rushn_attack",
    mission: str = "m1",
    extra_env: dict[str, str] | None = None,
) -> None:
    """FCEUX: -loadstate + Lua replay jsonl + achievement overlay."""
    fs = frame_skip if frame_skip is not None else fceux_frame_skip("inference")
    staged_rom, staged_state, staged_jsonl, staging = stage_playback(
        game=game,
        mission=mission,
        staging=staging,
        jsonl_path=jsonl_path,
    )
    tmp_dir.mkdir(parents=True, exist_ok=True)
    done_flag = tmp_dir / "done.flag"
    if done_flag.exists():
        done_flag.unlink()

    config_path = tmp_dir / "config.json"
    cfg: dict[str, Any] = {
        "jsonl_path": staged_jsonl.resolve().as_posix(),
        "episode": int(episode),
        "frame_skip": int(fs),
        "done_flag": done_flag.resolve().as_posix(),
        "turbo": bool(turbo),
    }
    if overlay_path and overlay_path.is_file():
        staged_overlay = staging / overlay_path.name
        shutil.copy2(overlay_path, staged_overlay)
        cfg["overlay_path"] = staged_overlay.resolve().as_posix()

    config_path.write_text(json.dumps(cfg), encoding="utf-8")

    lua = repo_root() / "fceux" / "lua" / "achievement_overlay.lua"
    extra = ["-loadstate", staged_state.name]
    if turbo:
        extra.extend(["-nothrottle", "1"])

    frames = replay_frame_count(jsonl_path, episode, frame_skip=fs)
    hold = 180
    if overlay_path and overlay_path.is_file():
        try:
            hold = int(json.loads(overlay_path.read_text(encoding="utf-8")).get("show_until_frame", 180))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    timeout = max(timeout_sec, (frames + hold) / 30.0 + 15.0)

    run_fceux_lua(
        lua,
        config_path,
        staging,
        staged_rom,
        timeout_sec=timeout,
        done_flag=done_flag,
        noicon=False,
        turbo=turbo,
        extra_args=extra,
        extra_env=extra_env,
    )
    if not done_flag.is_file():
        raise RuntimeError("inference playback finished without done.flag")


def probe_playback_overlay_ppu(
    jsonl_path: Path,
    episode: int,
    staging: Path,
    tmp_dir: Path,
    screenshot_path: Path,
    *,
    probe_at_frame: int = PROBE_RESET_FRAME,
    frame_skip: int | None = None,
    timeout_sec: float = 90.0,
    game: str = "rushn_attack",
    mission: str = "m1",
) -> dict:
    """Smoke: achievement_overlay.lua (register hooks) + PPU @ probe frame."""
    from fm2_playback import gd_screenshot_to_png, ppu_screenshot_heuristic

    fs = frame_skip if frame_skip is not None else fceux_frame_skip("inference")
    staged_rom, staged_state, staged_jsonl, staging = stage_playback(
        game=game,
        mission=mission,
        staging=staging,
        jsonl_path=jsonl_path,
    )
    tmp_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    gd_path = Path(str(screenshot_path) + ".gd")
    for p in (screenshot_path, gd_path):
        if p.exists():
            p.unlink()

    done_flag = tmp_dir / "done.flag"
    probe_flag = tmp_dir / "probe.json"
    for p in (done_flag, probe_flag):
        if p.exists():
            p.unlink()

    config_path = tmp_dir / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "jsonl_path": staged_jsonl.resolve().as_posix(),
                "episode": int(episode),
                "frame_skip": int(fs),
                "done_flag": done_flag.resolve().as_posix(),
                "turbo": False,
                "probe_at_frame": int(probe_at_frame),
                "probe_flag": probe_flag.resolve().as_posix(),
                "screenshot_path": screenshot_path.resolve().as_posix(),
                "probe_only": True,
            }
        ),
        encoding="utf-8",
    )

    lua = repo_root() / "fceux" / "lua" / "achievement_overlay.lua"
    timeout = max(timeout_sec, probe_at_frame * 0.25 + 30.0)
    run_fceux_lua(
        lua,
        config_path,
        staging,
        staged_rom,
        timeout_sec=timeout,
        done_flag=done_flag,
        noicon=True,
        turbo=False,
        extra_args=["-loadstate", staged_state.name],
    )
    if not probe_flag.is_file():
        return {"ok": False, "error": "probe_missing"}
    result = json.loads(probe_flag.read_text(encoding="utf-8"))
    png_path = screenshot_path.with_suffix(".png")
    if gd_screenshot_to_png(gd_path, png_path):
        result["screenshot_png"] = str(png_path)
    ppu = ppu_screenshot_heuristic(png_path if png_path.is_file() else gd_path)
    result["ppu_heuristic"] = ppu
    return result


def probe_inference_replay_visual(
    jsonl_path: Path,
    episode: int,
    staging: Path,
    tmp_dir: Path,
    screenshot_path: Path,
    *,
    ram: dict[str, int],
    probe_at_frame: int = 8,
    frame_skip: int | None = None,
    timeout_sec: float = 90.0,
    game: str = "rushn_attack",
    mission: str = "m1",
) -> dict:
    """RAM + PPU screenshot @ playback_frame (emulation+jsonl replay)."""
    fs = frame_skip if frame_skip is not None else fceux_frame_skip("inference")
    staged_rom, staged_state, staged_jsonl, staging = stage_playback(
        game=game,
        mission=mission,
        staging=staging,
        jsonl_path=jsonl_path,
    )
    tmp_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    gd_path = Path(str(screenshot_path) + ".gd")
    for p in (screenshot_path, gd_path):
        if p.exists():
            p.unlink()

    done_flag = tmp_dir / "done.flag"
    probe_flag = tmp_dir / "probe.json"
    for p in (done_flag, probe_flag):
        if p.exists():
            p.unlink()

    config_path = tmp_dir / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "jsonl_path": staged_jsonl.resolve().as_posix(),
                "episode": int(episode),
                "frame_skip": int(fs),
                "probe_at_frame": int(probe_at_frame),
                "probe_flag": probe_flag.resolve().as_posix(),
                "screenshot_path": screenshot_path.resolve().as_posix(),
                "done_flag": done_flag.resolve().as_posix(),
                **ram,
            }
        ),
        encoding="utf-8",
    )

    lua = repo_root() / "fceux" / "lua" / "inference_replay_visual_probe.lua"
    timeout = max(timeout_sec, probe_at_frame * 0.25 + 30.0)
    run_fceux_lua(
        lua,
        config_path,
        staging,
        staged_rom,
        timeout_sec=timeout,
        done_flag=done_flag,
        noicon=True,
        turbo=False,
        extra_args=["-loadstate", staged_state.name],
    )
    if not probe_flag.is_file():
        return {"ok": False, "error": "probe_missing"}
    result = json.loads(probe_flag.read_text(encoding="utf-8"))
    result["screenshot_gd"] = str(gd_path)
    result["screenshot_file"] = str(screenshot_path)
    return result


def probe_inference_replay_ppu(
    jsonl_path: Path,
    episode: int,
    staging: Path,
    tmp_dir: Path,
    *,
    ram: dict[str, int],
    probe_at_frame: int = 8,
    frame_skip: int | None = None,
    timeout_sec: float = 90.0,
    game: str = "rushn_attack",
    mission: str = "m1",
) -> dict:
    """Visual probe + PPU heuristic (N4)."""
    from fm2_playback import gd_screenshot_to_png, ppu_screenshot_heuristic

    shot = tmp_dir / f"jsonl_ep{episode}_f{probe_at_frame}.png"
    result = probe_inference_replay_visual(
        jsonl_path,
        episode,
        staging,
        tmp_dir,
        shot,
        ram=ram,
        probe_at_frame=probe_at_frame,
        frame_skip=frame_skip,
        timeout_sec=timeout_sec,
        game=game,
        mission=mission,
    )
    gd_path = Path(result.get("screenshot_gd_path") or str(shot) + ".gd")
    png_path = shot.with_suffix(".png")
    if gd_screenshot_to_png(gd_path, png_path):
        result["screenshot_png"] = str(png_path)
        result["screenshot_exists"] = True
    ppu = ppu_screenshot_heuristic(png_path if png_path.is_file() else gd_path)
    result["ppu_heuristic"] = ppu
    return result
