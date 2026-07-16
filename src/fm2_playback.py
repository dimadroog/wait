"""FM2 playback staging helpers for FCEUX CLI."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from fceux_launch import run_fceux_lua, run_fceux_movie
from fm2_export import (
    PLAYBACK_SAVESTATE_NAME,
    ensure_savestate_movie_guid,
    episode_fm2_guid,
    refresh_fm2_embedded_savestate,
    remap_fm2_guid,
    stage_playback_savestate,
)
from project_paths import parse_fm2_rom_basename, repo_root


def stage_playback_fc0(
    inference_fc0: Path,
    staging: Path,
    *,
    guid: str,
    state_name: str = PLAYBACK_SAVESTATE_NAME,
) -> Path:
    """playback.fc0 из inference_cp0 + GUID клипа."""
    staging.mkdir(parents=True, exist_ok=True)
    dest = staging / state_name
    dest.write_bytes(ensure_savestate_movie_guid(inference_fc0.read_bytes(), guid))
    return dest


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


def stage_external_playback(
    staged_fm2: Path,
    staging: Path,
    *,
    fallback_fc0: Path | None = None,
) -> Path:
    """playback.fc0 в staging из embed FM2 (или fallback .fc0)."""
    return stage_playback_savestate(
        staged_fm2,
        staging,
        fallback_fc0=fallback_fc0,
        state_name=PLAYBACK_SAVESTATE_NAME,
    )


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
    """RAM-probe при -playmovie (ISSUE_INFERENCE N4)."""
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
    staged_paths: tuple[Path, Path] | None = None,
) -> dict:
    """RAM + gui.savescreenshot @ mf (N6 visual verification)."""
    if staged_paths is not None:
        staged_fm2, staged_rom = staged_paths
    else:
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


def stage_play_inference_clip(
    fm2: Path,
    rom: Path,
    staging: Path,
    *,
    guid_salt: str,
    inference_fc0: Path,
) -> tuple[Path, Path]:
    """Staging как play_inference_fm2: remap GUID + refresh embed."""
    staging.mkdir(parents=True, exist_ok=True)
    staged_fm2 = staging / "playback.fm2"
    shutil.copy2(fm2, staged_fm2)
    clip_guid = episode_fm2_guid(salt=guid_salt)
    remap_fm2_guid(staged_fm2, clip_guid)
    refresh_fm2_embedded_savestate(staged_fm2, inference_fc0, guid=clip_guid)
    rom_base = parse_fm2_rom_basename(fm2)
    staged_rom = staging / rom_base
    for name in (rom_base, rom_base + ".nes", rom.name):
        shutil.copy2(rom, staging / name)
    return staged_fm2, staged_rom


def _stage_rom(rom: Path, staging: Path) -> Path:
    """ROM в staging (без loadstate)."""
    staging.mkdir(parents=True, exist_ok=True)
    rom_base = rom.stem if rom.suffix.lower() == ".nes" else rom.name
    staged_rom = staging / rom_base
    for name in (rom_base, rom_base + ".nes", rom.name):
        shutil.copy2(rom, staging / name)
    return staged_rom


def _stage_rom_loadstate(
    rom: Path,
    loadstate: Path,
    staging: Path,
) -> tuple[Path, Path, Path]:
    """ROM + .fc0 в staging для -loadstate (N6 record probe)."""
    staged_rom = _stage_rom(rom, staging)
    staged_state = staging / loadstate.name
    shutil.copy2(loadstate, staged_state)
    return staged_rom, staged_state, staging / rom.name


def _mirror_fc0_to_fcs(loadstate: Path, rom: Path, *, slot: int = 0) -> Path:
    """Копия .fc0 в fceux/portable/fcs/ для savestate.load(slot) (N6-C)."""
    from project_paths import resolve_fceux_home

    rom_base = rom.stem if rom.suffix.lower() == ".nes" else rom.name
    fcs_dir = resolve_fceux_home() / "fcs"
    fcs_dir.mkdir(parents=True, exist_ok=True)
    dest = fcs_dir / f"{rom_base}.fc{slot}"
    shutil.copy2(loadstate, dest)
    return dest


def probe_native_record_replay(
    rom: Path,
    out_fm2: Path,
    tmp_dir: Path,
    *,
    ram: dict[str, int],
    variant: str = "N6-B",
    save_type: int = 1,
    loadstate: Path | None = None,
    num_record_frames: int = 60,
    probe_at_mf: int = 8,
    savestate_slot: int = 0,
    require_gameplay_ram: bool | None = None,
    load_slot_before_record: bool = False,
    timeout_sec: float = 120.0,
    noicon: bool = False,
) -> dict:
    """N6: movie.record → stop → play → RAM-probe (вне пайплайна)."""
    if require_gameplay_ram is None:
        require_gameplay_ram = variant != "N6-A"

    staging = tmp_dir / "staging"
    extra_args: list[str] | None = None

    if variant == "N6-B":
        if loadstate is None or not loadstate.is_file():
            return {"ok": False, "error": "loadstate_required", "variant": variant}
        staged_rom, staged_state, _ = _stage_rom_loadstate(rom, loadstate, staging)
        extra_args = ["-loadstate", staged_state.name]
    elif variant == "N6-C":
        if loadstate is None or not loadstate.is_file():
            return {"ok": False, "error": "loadstate_required", "variant": variant}
        staged_rom = _stage_rom(rom, staging)
        _mirror_fc0_to_fcs(loadstate, rom, slot=savestate_slot)
        load_slot_before_record = True
    elif variant == "F0":
        if loadstate is None or not loadstate.is_file():
            return {"ok": False, "error": "loadstate_required", "variant": variant}
        staged_rom, staged_state, _ = _stage_rom_loadstate(rom, loadstate, staging)
        extra_args = ["-loadstate", staged_state.name]
        load_slot_before_record = True
    else:
        staged_rom = _stage_rom(rom, staging)

    tmp_dir.mkdir(parents=True, exist_ok=True)
    out_fm2.parent.mkdir(parents=True, exist_ok=True)
    if out_fm2.exists():
        out_fm2.unlink()

    done_flag = tmp_dir / "done.flag"
    result_flag = tmp_dir / "result.json"
    for p in (done_flag, result_flag):
        if p.exists():
            p.unlink()

    config_path = tmp_dir / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "done_flag": done_flag.resolve().as_posix(),
                "result_flag": result_flag.resolve().as_posix(),
                "out_fm2": out_fm2.resolve().as_posix(),
                "variant": variant,
                "num_record_frames": num_record_frames,
                "probe_at_mf": probe_at_mf,
                "save_type": save_type,
                "savestate_slot": savestate_slot,
                "require_gameplay_ram": require_gameplay_ram,
                "load_slot_before_record": load_slot_before_record,
                **ram,
            }
        ),
        encoding="utf-8",
    )
    lua = repo_root() / "fceux" / "lua" / "movie_record_replay_probe.lua"
    run_fceux_lua(
        lua,
        config_path,
        staging,
        staged_rom,
        timeout_sec,
        done_flag=done_flag,
        noicon=noicon,
        extra_args=extra_args,
    )
    if not result_flag.is_file():
        return {"ok": False, "error": "result_missing", "variant": variant}
    result = json.loads(result_flag.read_text(encoding="utf-8"))
    result["out_fm2"] = str(out_fm2)
    if out_fm2.is_file():
        from fm2_export import fm2_has_embedded_savestate, read_embedded_savestate_blob

        text_head = out_fm2.read_text(encoding="utf-8", errors="replace").splitlines()
        embed_line = next(
            (ln for ln in text_head if ln.startswith("savestate ") and not ln.startswith("|")),
            "",
        )
        result["fm2_on_disk"] = True
        result["fm2_size"] = out_fm2.stat().st_size
        result["embed_line_prefix"] = embed_line.split(None, 1)[0] if embed_line else None
        result["has_embed"] = bool(embed_line) or fm2_has_embedded_savestate(out_fm2)
        blob = read_embedded_savestate_blob(out_fm2)
        if blob is None and embed_line.startswith("savestate base64:"):
            import base64

            b64 = embed_line.split(":", 1)[1].strip()
            try:
                blob = base64.b64decode(b64)
            except (ValueError, TypeError):
                blob = None
        result["embed_size"] = len(blob) if blob else 0
    else:
        result["fm2_on_disk"] = False
        result["has_embed"] = False
        result["embed_size"] = 0
    return result


def run_f0_operator_gate(
    rom: Path,
    loadstate: Path,
    bench_dir: Path,
    *,
    ram: dict[str, int],
    probe_mfs: tuple[int, ...] = (8, 28),
    num_record_frames: int = 60,
    noicon_record: bool = True,
    noicon_visual: bool = False,
    timeout_sec: float = 120.0,
) -> dict:
    """F-proto F0: emulation capture → native record → PPU gate @ mf=8, 28."""
    bench_dir.mkdir(parents=True, exist_ok=True)
    record_dir = bench_dir / "record"
    out_fm2 = bench_dir / "f0_native.fm2"
    record = probe_native_record_replay(
        rom,
        out_fm2,
        record_dir,
        ram=ram,
        variant="F0",
        loadstate=loadstate,
        num_record_frames=num_record_frames,
        probe_at_mf=probe_mfs[0],
        noicon=noicon_record,
        timeout_sec=timeout_sec,
    )
    visual: dict[str, dict] = {}
    for mf in probe_mfs:
        staging = bench_dir / f"play_staging_mf{mf}"
        tmp = bench_dir / f"play_tmp_mf{mf}"
        shot = bench_dir / f"f0_visual_mf{mf}.png"
        probe = probe_movie_playback_visual(
            out_fm2,
            rom,
            staging,
            tmp,
            shot,
            ram=ram,
            probe_at_mf=mf,
            timeout_sec=timeout_sec,
            noicon=noicon_visual,
        )
        gd_path = Path(probe.get("screenshot_gd_path") or str(shot) + ".gd")
        png_path = shot.with_suffix(".png")
        if gd_screenshot_to_png(gd_path, png_path):
            probe["screenshot_png"] = str(png_path)
        probe["ppu_heuristic"] = ppu_screenshot_heuristic(
            png_path if png_path.is_file() else gd_path
        )
        visual[str(mf)] = probe

    ppu_gameplay = all(
        (visual[str(mf)].get("ppu_heuristic") or {}).get("gameplay_like_ppu_heuristic") is True
        for mf in probe_mfs
    )
    ram_pass = record.get("ok") is True
    operator_pass = ram_pass and ppu_gameplay

    summary = {
        "phase": "F0",
        "variant": "F0",
        "record": record,
        "visual": visual,
        "verdict": {
            "ram_pass": ram_pass,
            "ppu_gameplay": ppu_gameplay,
            "operator_pass": operator_pass,
            "operator_note": (
                "PASS" if operator_pass else "FAIL — PPU heuristic @ mf=8/28 (GUI оператор подтверждает)"
            ),
        },
        "out_fm2": str(out_fm2),
    }
    out_path = bench_dir / "f0_results.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    summary["results_path"] = str(out_path)
    return summary


def gd_screenshot_to_png(gd_path: Path, png_path: Path) -> bool:
    """Конвертация gui.gdscreenshot → PNG (N6 visual / N4 PPU assert)."""
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
        import numpy as np
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
    """RAM + PPU heuristic @ mf (N4 visual assert)."""
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
    gd_path = Path(result.get("screenshot_gd_path") or str(shot) + ".gd")
    png_path = shot.with_suffix(".png")
    if gd_screenshot_to_png(gd_path, png_path):
        result["screenshot_png"] = str(png_path)
    ppu = ppu_screenshot_heuristic(png_path if png_path.is_file() else gd_path)
    result["ppu_heuristic"] = ppu
    return result
