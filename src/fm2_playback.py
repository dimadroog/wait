"""FM2 playback helpers: playmovie argv + regression probes (G0)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from fceux_launch import run_fceux_movie
from project_paths import parse_fm2_rom_basename, repo_root


def fceux_playmovie_argv(
    *,
    staged_fm2: Path,
    staged_rom: Path,
) -> list[str]:
    """Self-contained FM2: -playmovie embed -readonly 1 rom."""
    return [
        "-playmovie",
        staged_fm2.name,
        "-readonly",
        "1",
        staged_rom.name,
    ]


def _stage_fm2_rom(fm2: Path, rom: Path, staging: Path) -> tuple[Path, Path]:
    staging.mkdir(parents=True, exist_ok=True)
    staged_fm2 = staging / fm2.name
    shutil.copy2(fm2, staged_fm2)
    rom_base = parse_fm2_rom_basename(fm2)
    staged_rom = staging / rom_base
    for name in (rom_base, rom_base + ".nes", rom.name):
        shutil.copy2(rom, staging / name)
    return staged_fm2, staged_rom


def probe_movie_playback(
    fm2_path: Path,
    rom: Path,
    staging: Path,
    tmp_dir: Path,
    *,
    ram: dict[str, int],
    probe_at_mf: int = 8,
    timeout_sec: float = 60.0,
) -> dict:
    """RAM-probe при -playmovie (регрессия embed / gameplay_start)."""
    staged_fm2, staged_rom = _stage_fm2_rom(fm2_path, rom, staging)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    done_flag = tmp_dir / "done.flag"
    probe_flag = tmp_dir / "probe.json"
    for p in (done_flag, probe_flag):
        if p.exists():
            p.unlink()
    config_path = tmp_dir / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "done_flag": done_flag.resolve().as_posix(),
                "probe_flag": probe_flag.resolve().as_posix(),
                "probe_at_mf": probe_at_mf,
                **ram,
            }
        ),
        encoding="utf-8",
    )
    lua = repo_root() / "fceux" / "lua" / "movie_playback_probe.lua"
    run_fceux_movie(
        staged_fm2,
        staged_rom,
        lua,
        config_path,
        cwd=staging,
        timeout_sec=timeout_sec,
        done_flag=done_flag,
        noicon=False,
    )
    if not probe_flag.is_file():
        return {"ok": False, "error": "probe_missing"}
    return json.loads(probe_flag.read_text(encoding="utf-8"))


def probe_movie_playback_visual(
    fm2_path: Path,
    rom: Path,
    staging: Path,
    tmp_dir: Path,
    screenshot_path: Path,
    *,
    ram: dict[str, int],
    probe_at_mf: int = 8,
    timeout_sec: float = 90.0,
    noicon: bool = False,
) -> dict:
    """RAM + gui.gdscreenshot @ mf."""
    staged_fm2, staged_rom = _stage_fm2_rom(fm2_path, rom, staging)
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
                "done_flag": done_flag.resolve().as_posix(),
                "probe_flag": probe_flag.resolve().as_posix(),
                "screenshot_path": screenshot_path.resolve().as_posix(),
                "probe_at_mf": probe_at_mf,
                **ram,
            }
        ),
        encoding="utf-8",
    )
    lua = repo_root() / "fceux" / "lua" / "movie_playback_visual_probe.lua"
    run_fceux_movie(
        staged_fm2,
        staged_rom,
        lua,
        config_path,
        cwd=staging,
        timeout_sec=timeout_sec,
        done_flag=done_flag,
        noicon=noicon,
    )
    if not probe_flag.is_file():
        return {"ok": False, "error": "probe_missing"}
    result = json.loads(probe_flag.read_text(encoding="utf-8"))
    result["screenshot_gd"] = str(gd_path)
    result["screenshot_file"] = str(screenshot_path)
    result["screenshot_exists"] = screenshot_path.is_file()
    return result


def gd_screenshot_to_png(gd_path: Path, png_path: Path) -> bool:
    """Конвертация gui.gdscreenshot → PNG."""
    if not gd_path.is_file():
        return False
    try:
        import cv2
        import numpy as np

        from fceux_bridge import GD_HEADER_BYTES, NES_HEIGHT, NES_WIDTH
    except ImportError:
        return False
    gd_bytes = gd_path.read_bytes()
    expected = GD_HEADER_BYTES + NES_WIDTH * NES_HEIGHT * 4
    if len(gd_bytes) != expected:
        return False
    rgba = np.frombuffer(gd_bytes[GD_HEADER_BYTES:], dtype=np.uint8).reshape(NES_HEIGHT, NES_WIDTH, 4)
    bgr = cv2.cvtColor(rgba[:, :, :3], cv2.COLOR_RGB2BGR)
    return bool(cv2.imwrite(str(png_path), bgr))


def ppu_screenshot_heuristic(path: Path) -> dict:
    """Эвристика title vs gameplay по центральному crop скриншота."""
    if not path.is_file():
        return {"ok": False, "error": "missing"}
    try:
        import cv2
    except ImportError:
        return {"ok": False, "error": "opencv not installed"}
    img = cv2.imread(str(path))
    if img is None:
        return {"ok": False, "error": "unreadable"}
    h, w = img.shape[:2]
    cx0, cy0 = w // 4, h // 4
    cx1, cy1 = 3 * w // 4, 3 * h // 4
    crop = img[cy0:cy1, cx0:cx1]
    pixels = crop.reshape(-1, 3)
    n = len(pixels)
    if n == 0:
        return {"ok": False, "error": "empty"}
    mean_bgr = pixels.mean(axis=0)
    dark_frac = float((pixels.max(axis=1) < 40).mean())
    quantized = (pixels // 16).reshape(-1)
    unique = len({(quantized[i], quantized[i + 1], quantized[i + 2]) for i in range(0, len(quantized), 3)})
    title_like = unique < 15 and dark_frac > 0.6
    return {
        "ok": True,
        "size": [w, h],
        "mean_bgr": [round(float(x), 1) for x in mean_bgr],
        "dark_frac": round(dark_frac, 4),
        "unique_colors_center": unique,
        "title_like": title_like,
        "gameplay_like_ppu_heuristic": not title_like,
    }


def probe_movie_playback_ppu(
    fm2_path: Path,
    rom: Path,
    staging: Path,
    tmp_dir: Path,
    *,
    ram: dict[str, int],
    probe_at_mf: int = 8,
    timeout_sec: float = 90.0,
) -> dict:
    """RAM + PPU heuristic @ mf (регрессия G0: не title на inference_cp0)."""
    shot = tmp_dir / f"ppu_mf{probe_at_mf}.png"
    result = probe_movie_playback_visual(
        fm2_path,
        rom,
        staging,
        tmp_dir,
        shot,
        ram=ram,
        probe_at_mf=probe_at_mf,
        timeout_sec=timeout_sec,
        noicon=False,
    )
    gd_path = Path(result.get("screenshot_gd") or str(shot) + ".gd")
    png_path = shot.with_suffix(".png")
    if gd_screenshot_to_png(gd_path, png_path):
        result["screenshot_png"] = str(png_path)
        result["screenshot_ok"] = True
    else:
        result["screenshot_ok"] = png_path.is_file() or gd_path.is_file()
    ppu = ppu_screenshot_heuristic(png_path if png_path.is_file() else gd_path)
    result["ppu_heuristic"] = ppu
    return result
