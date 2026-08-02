"""FM2-synced запись reference/demos_for_bc/seg_*.npz (BC)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from demo_quality import SegmentQualityResult, evaluate_segment_quality
from fceux_bridge import decode_raw_obs
from fceux_launch import fceux_sound_off
from obs_contract import OBS_HEIGHT, OBS_SHAPE, OBS_WIDTH
from playthrough_build import gameplay_start_frame_from_head_saves, load_head_save_states
from project_paths import demos_for_bc_dir, game_dir, load_yaml, repo_root, resolve_fceux_binary, resolve_rom
from ram_scout import stage_fm2
from train.action_map import action_string_to_index

RECORD_MODE = "fm2_playmovie"
DEFAULT_FRAME_SKIP = 4
DEFAULT_TIMEOUT_SEC = 600.0


@dataclass(frozen=True)
class SampleRow:
    frame: int
    obs_path: Path


@dataclass(frozen=True)
class RecordResult:
    segment_id: str
    path: Path
    n_steps: int
    quality: SegmentQualityResult


def _load_human_by_frame(human_path: Path) -> dict[int, str]:
    by_frame: dict[int, str] = {}
    with human_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                row = json.loads(line)
                by_frame[int(row["frame"])] = str(row.get("action", ""))
    return by_frame


def _load_action_strings(game_id: str) -> list[str]:
    cfg = load_yaml(game_dir(game_id) / "env_config.yaml")
    return [str(a) for a in (cfg.get("actions") or [])]


def _segment_for_frame(
    segments: list[dict[str, Any]],
    frame: int,
    *,
    frame_skip: int,
) -> dict[str, Any] | None:
    for seg in segments:
        start = int(seg["frame_start"])
        end = int(seg["frame_end"])
        if start <= frame <= end and (frame - start) % frame_skip == 0:
            return seg
    return None


def _obs_stack_from_deque(frames: deque[np.ndarray]) -> np.ndarray:
    stack = list(frames)
    while len(stack) < 4:
        stack.insert(0, stack[0].copy())
    return np.stack(stack[-4:], axis=0).astype(np.float32) / 255.0


def _partition_samples(
    rows: list[SampleRow],
    *,
    segments: list[dict[str, Any]],
    human_by_frame: dict[int, str],
    action_strings: list[str],
    frame_skip: int,
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    buffers: dict[str, tuple[list[np.ndarray], list[int]]] = {
        str(seg["id"]): ([], []) for seg in segments
    }
    frame_deque: deque[np.ndarray] = deque(maxlen=4)

    for row in rows:
        seg = _segment_for_frame(segments, row.frame, frame_skip=frame_skip)
        if seg is None:
            continue
        seg_id = str(seg["id"])
        if int(row.frame) == int(seg["frame_start"]):
            frame_deque.clear()
        gray = decode_raw_obs(row.obs_path)
        frame_deque.append(gray)
        obs_stack = _obs_stack_from_deque(frame_deque)
        action_idx = action_string_to_index(
            human_by_frame.get(row.frame, ""), action_strings
        )
        obs_list, act_list = buffers[seg_id]
        obs_list.append(obs_stack)
        act_list.append(action_idx)

    out: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for seg_id, (obs_list, act_list) in buffers.items():
        if not obs_list:
            out[seg_id] = (
                np.zeros((0, *OBS_SHAPE), dtype=np.float32),
                np.zeros((0,), dtype=np.int64),
            )
        else:
            out[seg_id] = (
                np.stack(obs_list, axis=0),
                np.asarray(act_list, dtype=np.int64),
            )
    return out


def _write_config(
    path: Path,
    *,
    ipc_dir: Path,
    samples_jsonl: Path,
    done_flag: Path,
    frame_skip: int,
    segments: list[dict[str, Any]],
) -> None:
    payload = {
        "ipc_dir": ipc_dir.as_posix(),
        "samples_jsonl": samples_jsonl.as_posix(),
        "done_flag": done_flag.as_posix(),
        "frame_skip": frame_skip,
        "obs_w": OBS_WIDTH,
        "obs_h": OBS_HEIGHT,
        "segments": [
            {
                "id": seg["id"],
                "frame_start": int(seg["frame_start"]),
                "frame_end": int(seg["frame_end"]),
            }
            for seg in segments
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def run_fceux_demos_capture(
    staged_fm2: Path,
    staged_rom: Path,
    config_path: Path,
    *,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
) -> None:
    fceux = resolve_fceux_binary()
    lua = repo_root() / "fceux" / "lua" / "demos_for_bc.lua"
    env = os.environ.copy()
    env["WAIT_DEMOS_BC_CONFIG"] = str(config_path.resolve())

    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    done_flag = Path(cfg["done_flag"])
    if done_flag.exists():
        done_flag.unlink()

    cmd = [
        str(fceux),
        "-readonly",
        "1",
        "-turbo",
        "1",
        "-nothrottle",
        "1",
        "-noicon",
        "1",
        "-lua",
        str(lua),
        "-playmovie",
        staged_fm2.name,
        staged_rom.name,
    ]

    with fceux_sound_off(fceux.parent):
        proc = subprocess.Popen(
            cmd,
            cwd=str(staged_fm2.parent),
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )

        deadline = time.time() + timeout_sec
        while proc.poll() is None:
            if done_flag.is_file():
                proc.wait(timeout=60)
                return
            if time.time() > deadline:
                proc.terminate()
                raise TimeoutError(f"FCEUX demos_for_bc timeout ({timeout_sec}s)")
            time.sleep(0.2)

        if proc.returncode not in (0, None):
            raise RuntimeError(f"FCEUX exited with code {proc.returncode}")


def load_sample_rows(samples_jsonl: Path) -> list[SampleRow]:
    rows: list[SampleRow] = []
    with samples_jsonl.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            rows.append(SampleRow(frame=int(row["frame"]), obs_path=Path(str(row["obs"]))))
    rows.sort(key=lambda r: r.frame)
    return rows


def write_demo_npz(
    path: Path,
    *,
    obs: np.ndarray,
    actions: np.ndarray,
    seg: dict[str, Any],
    mission_id: str,
    frame_skip: int,
    fm2_rel: str,
    gameplay_start_frame: int | None,
    quality: SegmentQualityResult,
) -> None:
    segment_meta_json = json.dumps(
        {
            "segment_id": seg["id"],
            "mission": mission_id,
            "frame_start": int(seg["frame_start"]),
            "frame_end": int(seg["frame_end"]),
            "frame_skip": frame_skip,
            "obs_w": OBS_WIDTH,
            "obs_h": OBS_HEIGHT,
            "obs_shape": list(OBS_SHAPE),
            "record_mode": RECORD_MODE,
            "fm2_file": fm2_rel,
            "gameplay_start_frame": gameplay_start_frame,
            "quality": {
                "black_fraction": round(quality.metrics.black_fraction, 4),
                "obs_std": round(quality.metrics.obs_std, 4),
                "gameplay_fraction": round(quality.metrics.gameplay_fraction, 4),
                "obs_max": round(quality.metrics.obs_max, 4),
                "passed": quality.passed,
            },
        },
        ensure_ascii=False,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, obs=obs, actions=actions, meta=np.array(segment_meta_json))


def record_demos_fm2(
    mission: Path,
    game_id: str,
    mission_id: str,
    fm2: Path,
    *,
    segment_ids: list[str] | None = None,
    frame_skip: int = DEFAULT_FRAME_SKIP,
    session_subdir: str = "demos_for_bc",
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    strict_quality: bool = True,
) -> list[RecordResult]:
    """Один проход clear.fm2 → seg_*.npz с FM2-synced obs."""
    manifest_path = mission / "config" / "playthrough_manifest.yaml"
    human_path = mission / "reference" / "human_playthrough.jsonl"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"manifest not found: {manifest_path}")
    if not human_path.is_file():
        raise FileNotFoundError(f"human_playthrough.jsonl not found: {human_path}")
    if not fm2.is_file():
        raise FileNotFoundError(f"FM2 not found: {fm2}")

    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    segments: list[dict[str, Any]] = list(manifest.get("segments") or [])
    if segment_ids:
        wanted = set(segment_ids)
        segments = [s for s in segments if s.get("id") in wanted]
        missing = wanted - {str(s.get("id")) for s in segments}
        if missing:
            raise ValueError(f"unknown segment ids: {sorted(missing)}")
    if not segments:
        raise ValueError("no segments to record")

    head_saves = load_head_save_states(mission)
    gameplay_start = gameplay_start_frame_from_head_saves(head_saves)
    train_block = manifest.get("train") or {}
    if gameplay_start is None and train_block.get("gameplay_start_frame") is not None:
        gameplay_start = int(train_block["gameplay_start_frame"])

    fm2_rel = str(manifest.get("fm2_file") or "reference/clear.fm2")
    human_by_frame = _load_human_by_frame(human_path)
    action_strings = _load_action_strings(game_id)

    work_root = repo_root() / "tmp" / session_subdir
    if work_root.exists():
        shutil.rmtree(work_root, ignore_errors=True)
    staging = work_root / "staging"
    ipc_dir = work_root / "ipc"
    ipc_dir.mkdir(parents=True)
    samples_jsonl = work_root / "samples.jsonl"
    done_flag = work_root / "done.flag"
    config_path = work_root / "config.json"

    rom = resolve_rom(game_id)
    staged_fm2, staged_rom = stage_fm2(fm2, rom, staging)
    _write_config(
        config_path,
        ipc_dir=ipc_dir,
        samples_jsonl=samples_jsonl,
        done_flag=done_flag,
        frame_skip=frame_skip,
        segments=segments,
    )

    print(f"Recording FM2 {fm2.name} -> {len(segments)} segment(s)...")
    run_fceux_demos_capture(staged_fm2, staged_rom, config_path, timeout_sec=timeout_sec)

    if not samples_jsonl.is_file():
        raise RuntimeError(f"samples.jsonl not created: {samples_jsonl}")

    all_rows = load_sample_rows(samples_jsonl)
    print(f"  captured {len(all_rows)} obs samples")

    partitioned = _partition_samples(
        all_rows,
        segments=segments,
        human_by_frame=human_by_frame,
        action_strings=action_strings,
        frame_skip=frame_skip,
    )

    demos_dir = demos_for_bc_dir(mission)
    demos_dir.mkdir(parents=True, exist_ok=True)

    results: list[RecordResult] = []
    failures: list[str] = []

    for seg in segments:
        seg_id = str(seg["id"])
        obs, actions = partitioned.get(
            seg_id,
            (np.zeros((0, *OBS_SHAPE), dtype=np.float32), np.zeros((0,), dtype=np.int64)),
        )
        if obs.shape[0] == 0:
            failures.append(f"{seg_id}: no samples")
            continue

        quality = evaluate_segment_quality(
            obs,
            segment_id=seg_id,
            frame_start=int(seg["frame_start"]),
            gameplay_start_frame=gameplay_start,
        )
        out = demos_dir / f"{seg_id}.npz"
        write_demo_npz(
            out,
            obs=obs,
            actions=actions,
            seg=seg,
            mission_id=mission_id,
            frame_skip=frame_skip,
            fm2_rel=fm2_rel,
            gameplay_start_frame=gameplay_start,
            quality=quality,
        )
        status = "ok" if quality.passed else "FAIL"
        print(
            f"  {seg_id}: N={obs.shape[0]} black={quality.metrics.black_fraction:.2f} "
            f"gameplay={quality.metrics.gameplay_fraction:.2f} [{status}]"
        )
        results.append(
            RecordResult(segment_id=seg_id, path=out, n_steps=int(obs.shape[0]), quality=quality)
        )
        if strict_quality and not quality.passed:
            failures.extend(f"{seg_id}: {r}" for r in quality.failure_reasons())

    if failures:
        raise SystemExit("Demo quality gate failed:\n  " + "\n  ".join(failures))

    return results
