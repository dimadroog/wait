"""Экспорт PNG-превью из reference/demos_for_bc/seg_*.npz (визуальная проверка BC)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import yaml

from demo_quality import SegmentQualityResult, validate_demo_npz
from obs_contract import OBS_WIDTH
from playthrough_build import gameplay_start_frame_from_head_saves, load_head_save_states
from project_paths import demos_for_bc_dir, game_dir, load_yaml, repo_root


@dataclass(frozen=True)
class PreviewResult:
    segment_id: str
    npz_path: Path
    out_dir: Path
    n_steps: int
    obs_max: float
    quality: SegmentQualityResult
    grid_path: Path | None
    sample_paths: list[Path]


def load_action_strings(game_id: str) -> list[str]:
    cfg = load_yaml(game_dir(game_id) / "env_config.yaml")
    raw = cfg.get("actions") or []
    return [str(a) for a in raw]


def decode_action(action_idx: int, action_strings: list[str]) -> str:
    i = int(action_idx)
    if 0 <= i < len(action_strings):
        return action_strings[i]
    return "?"


def _parse_meta(npz: np.lib.npyio.NpzFile) -> dict[str, Any]:
    raw = npz["meta"]
    text = raw.item() if hasattr(raw, "item") else raw
    return json.loads(str(text))


def _obs_tile(obs: np.ndarray, step: int, stack_index: int = -1) -> np.ndarray:
    """Последний кадр стека obs → uint8 grayscale."""
    plane = obs[step, stack_index]
    return (np.clip(plane, 0.0, 1.0) * 255.0).astype(np.uint8)


def _write_grid(
    obs: np.ndarray,
    *,
    out_path: Path,
    cols: int,
    tile_px: int,
) -> None:
    n = min(obs.shape[0], cols * cols)
    if n == 0:
        return
    tiles: list[np.ndarray] = []
    for i in range(n):
        tile = _obs_tile(obs, i)
        if tile_px != tile.shape[0]:
            tile = cv2.resize(tile, (tile_px, tile_px), interpolation=cv2.INTER_NEAREST)
        tiles.append(tile)
    rows: list[np.ndarray] = []
    for r in range(cols):
        row_tiles = tiles[r * cols : (r + 1) * cols]
        if not row_tiles:
            break
        while len(row_tiles) < cols:
            row_tiles.append(np.zeros((tile_px, tile_px), dtype=np.uint8))
        rows.append(np.hstack(row_tiles))
    grid = np.vstack(rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), grid)


def _gameplay_start_frame(mission: Path) -> int | None:
    head_saves = load_head_save_states(mission)
    gp = gameplay_start_frame_from_head_saves(head_saves)
    if gp is not None:
        return gp
    manifest_path = mission / "config" / "playthrough_manifest.yaml"
    if not manifest_path.is_file():
        return None
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    train_block = manifest.get("train") or {}
    raw = train_block.get("gameplay_start_frame")
    return int(raw) if raw is not None else None


def export_segment_preview(
    npz_path: Path,
    out_dir: Path,
    *,
    action_strings: list[str],
    quality: SegmentQualityResult,
    step_interval: int = 25,
    max_samples: int | None = 200,
    grid_cols: int = 5,
    tile_px: int = OBS_WIDTH,
) -> PreviewResult:
    """PNG-сетка + выборочные кадры для одного seg_*.npz."""
    with np.load(npz_path, allow_pickle=True) as z:
        meta = _parse_meta(z)
        obs = np.asarray(z["obs"], dtype=np.float32)
        actions = np.asarray(z["actions"], dtype=np.int64)

    seg_id = str(meta.get("segment_id") or npz_path.stem)
    frame_start = int(meta.get("frame_start", 0))
    frame_skip = int(meta.get("frame_skip", 1))
    n = min(int(obs.shape[0]), int(actions.shape[0]))

    seg_out = out_dir / seg_id
    seg_out.mkdir(parents=True, exist_ok=True)

    grid_path = seg_out / "grid.png"
    _write_grid(obs[:n], out_path=grid_path, cols=grid_cols, tile_px=tile_px)

    sample_paths: list[Path] = []
    limit = n if max_samples is None else min(n, max_samples)
    interval = max(1, int(step_interval))
    for step in range(0, limit, interval):
        fm_frame = frame_start + step * frame_skip
        img = _obs_tile(obs, step)
        fname = f"step_{step:04d}_fm{fm_frame}_a{decode_action(actions[step], action_strings).replace('+', '-') or 'noop'}.png"
        path = seg_out / fname
        cv2.imwrite(str(path), img)
        sample_paths.append(path)

    return PreviewResult(
        segment_id=seg_id,
        npz_path=npz_path,
        out_dir=seg_out,
        n_steps=n,
        obs_max=float(obs[:n].max()) if n else 0.0,
        quality=quality,
        grid_path=grid_path,
        sample_paths=sample_paths,
    )


def default_preview_out_dir() -> Path:
    return repo_root() / "tmp" / "demos_for_bc"


def export_all_demos(
    mission: Path,
    game_id: str,
    *,
    out_dir: Path | None = None,
    segment_ids: list[str] | None = None,
    step_interval: int = 25,
    max_samples: int | None = 200,
    grid_cols: int = 5,
    tile_px: int = OBS_WIDTH,
) -> tuple[Path, list[PreviewResult]]:
    """Экспорт превью для всех (или выбранных) seg_*.npz миссии."""
    demos_dir = demos_for_bc_dir(mission)
    if not demos_dir.is_dir():
        raise FileNotFoundError(f"demos_for_bc not found: {demos_dir}")

    paths = sorted(demos_dir.glob("seg_*.npz"))
    if segment_ids:
        wanted = set(segment_ids)
        paths = [p for p in paths if p.stem in wanted]
        missing = wanted - {p.stem for p in paths}
        if missing:
            raise ValueError(f"segment npz not found: {sorted(missing)}")

    if not paths:
        raise FileNotFoundError(f"no seg_*.npz in {demos_dir}")

    root = out_dir if out_dir is not None else default_preview_out_dir()
    root.mkdir(parents=True, exist_ok=True)

    gameplay_start = _gameplay_start_frame(mission)
    action_strings = load_action_strings(game_id)
    results: list[PreviewResult] = []
    for npz_path in paths:
        quality = validate_demo_npz(npz_path, gameplay_start_frame=gameplay_start)
        results.append(
            export_segment_preview(
                npz_path,
                root,
                action_strings=action_strings,
                quality=quality,
                step_interval=step_interval,
                max_samples=max_samples,
                grid_cols=grid_cols,
                tile_px=tile_px,
            )
        )

    index = {
        "mission": mission.as_posix(),
        "game_id": game_id,
        "source": demos_dir.as_posix(),
        "segments": [
            {
                "id": r.segment_id,
                "npz": r.npz_path.name,
                "n_steps": r.n_steps,
                "obs_max": round(r.obs_max, 4),
                "quality_passed": r.quality.passed,
                "black_fraction": round(r.quality.metrics.black_fraction, 4),
                "gameplay_fraction": round(r.quality.metrics.gameplay_fraction, 4),
                "out_dir": r.out_dir.relative_to(root).as_posix(),
                "grid": r.grid_path.relative_to(root).as_posix() if r.grid_path else None,
                "samples": len(r.sample_paths),
            }
            for r in results
        ],
    }
    index_path = root / "index.json"
    index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return root, results


def format_preview_summary(root: Path, results: list[PreviewResult]) -> list[str]:
    lines = [f"Preview: {root}"]
    for r in results:
        status = "ok" if r.quality.passed else "FAIL"
        lines.append(
            f"  {r.segment_id}: N={r.n_steps} obs_max={r.obs_max:.3f} "
            f"black={r.quality.metrics.black_fraction:.2f} "
            f"gameplay={r.quality.metrics.gameplay_fraction:.2f} [{status}] "
            f"grid={r.grid_path.name if r.grid_path else '-'} samples={len(r.sample_paths)}"
        )
    lines.append(f"index: {root / 'index.json'}")
    return lines


def quality_check_failures(results: list[PreviewResult]) -> list[str]:
    failures: list[str] = []
    for r in results:
        if not r.quality.passed:
            reasons = "; ".join(r.quality.failure_reasons())
            failures.append(f"{r.segment_id}: {reasons}")
    return failures
