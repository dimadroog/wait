"""Запись demos/seg_*.npz с реальными obs через Gymnasium env + FCEUX."""
from __future__ import annotations

import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from env.base_nes_env import BaseNesEnv
from env.loader import make_env
from train.action_map import action_string_to_index
from train.env_factory import cleanup_bridge_sessions

MAX_RECORD_WORKERS = 8


def _load_human_jsonl(path: Path) -> dict[int, dict[str, Any]]:
    by_frame: dict[int, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                row = json.loads(line)
                by_frame[int(row["frame"])] = row
    return by_frame


def _base_env(env) -> BaseNesEnv:
    base = env.unwrapped
    if not isinstance(base, BaseNesEnv):
        raise TypeError(f"Expected BaseNesEnv, got {type(base)}")
    return base


def record_segment(
    env,
    human_by_frame: dict[int, dict[str, Any]],
    seg: dict[str, Any],
    *,
    max_steps: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Replay сегмента эталона; один sample на env step (frame_skip)."""
    base = _base_env(env)
    frame_skip = int(base.frame_skip)
    start = int(seg["frame_start"])
    end = int(seg["frame_end"])
    save_state = str(seg.get("save_state", "states/cp0.fc0"))
    action_strings = base.action_strings

    obs, _info = env.reset(options={"save_state": save_state})

    obs_rows: list[np.ndarray] = []
    act_rows: list[int] = []

    frame = start
    steps = 0
    while frame <= end:
        row = human_by_frame.get(frame, {})
        action_idx = action_string_to_index(str(row.get("action", "")), action_strings)

        obs_rows.append(np.asarray(obs, dtype=np.float32))
        act_rows.append(action_idx)

        obs, _reward, terminated, truncated, _info = env.step(action_idx)
        steps += 1
        frame += frame_skip

        # Эталон уже пройден человеком — не обрываем сегмент на death penalty.
        if truncated:
            break
        if max_steps is not None and steps >= max_steps:
            break

    if not obs_rows:
        return np.zeros((0, 4, 84, 84), dtype=np.float32), np.zeros((0,), dtype=np.int64)

    return np.stack(obs_rows, axis=0), np.asarray(act_rows, dtype=np.int64)


def write_demo_npz(
    path: Path,
    *,
    obs: np.ndarray,
    actions: np.ndarray,
    seg: dict[str, Any],
    mission_id: str,
    frame_skip: int,
) -> None:
    meta = json.dumps(
        {
            "segment_id": seg["id"],
            "mission": mission_id,
            "frame_start": int(seg["frame_start"]),
            "frame_end": int(seg["frame_end"]),
            "frame_skip": frame_skip,
            "obs_stub": False,
        },
        ensure_ascii=False,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, obs=obs, actions=actions, meta=np.array(meta))


def default_record_workers(n_segments: int) -> int:
    """Число parallel FCEUX для record_demos (ML_CONCEPT §2: до 4–8 env)."""
    if n_segments <= 1:
        return 1
    cpu = os.cpu_count() or 4
    return max(1, min(n_segments, cpu, MAX_RECORD_WORKERS))


def _record_one_segment(
    mission: Path,
    game_id: str,
    mission_id: str,
    seg: dict[str, Any],
    *,
    human_path: Path,
    session_id: str,
    turbo: bool,
    max_steps: int | None,
) -> Path | None:
    """Один сегмент в отдельном процессе: свой FCEUX + bridge session."""
    seg_id = str(seg["id"])
    human_by_frame = _load_human_jsonl(human_path)
    demos_dir = mission / "demos"

    env = make_env(
        game_id,
        mission_id,
        wrap_rewards=False,
        session_id=session_id,
        turbo=turbo,
    )
    frame_skip = int(_base_env(env).frame_skip)
    try:
        print(f"Recording {seg_id} frames {seg['frame_start']}..{seg['frame_end']}...")
        obs, actions = record_segment(
            env,
            human_by_frame,
            seg,
            max_steps=max_steps,
        )
        if obs.shape[0] == 0:
            print(f"  skip {seg_id}: no transitions")
            return None
        out = demos_dir / f"{seg_id}.npz"
        write_demo_npz(
            out,
            obs=obs,
            actions=actions,
            seg=seg,
            mission_id=mission_id,
            frame_skip=frame_skip,
        )
        print(
            f"  wrote {out.name}: N={obs.shape[0]} "
            f"obs=[{obs.min():.3f},{obs.max():.3f}]"
        )
        return out
    finally:
        env.close()


def _record_segment_job(
    mission_str: str,
    game_id: str,
    mission_id: str,
    seg: dict[str, Any],
    *,
    human_path_str: str,
    rank: int,
    session_prefix: str,
    turbo: bool,
    max_steps: int | None,
) -> str | None:
    out = _record_one_segment(
        Path(mission_str),
        game_id,
        mission_id,
        seg,
        human_path=Path(human_path_str),
        session_id=f"{session_prefix}_{rank}",
        turbo=turbo,
        max_steps=max_steps,
    )
    return str(out) if out is not None else None


def record_demos(
    mission: Path,
    game_id: str,
    mission_id: str,
    *,
    segment_ids: list[str] | None = None,
    session_id: str = "record_demos",
    turbo: bool = True,
    max_steps: int | None = None,
    workers: int | None = None,
) -> list[Path]:
    """Пересобирает demos/seg_*.npz с obs из env (BC / ML_CONCEPT §8)."""
    manifest_path = mission / "config" / "playthrough_manifest.yaml"
    human_path = mission / "reference" / "human_playthrough.jsonl"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"manifest not found: {manifest_path}")
    if not human_path.is_file():
        raise FileNotFoundError(f"human_playthrough.jsonl not found: {human_path}")

    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    segments: list[dict[str, Any]] = list(manifest.get("segments") or [])
    if segment_ids:
        wanted = set(segment_ids)
        segments = [s for s in segments if s.get("id") in wanted]
        missing = wanted - {s.get("id") for s in segments}
        if missing:
            raise ValueError(f"Unknown segment ids: {sorted(missing)}")

    n_workers = workers if workers is not None else default_record_workers(len(segments))
    n_workers = max(1, min(n_workers, len(segments), MAX_RECORD_WORKERS))
    written: list[Path] = []

    if n_workers == 1:
        human_by_frame = _load_human_jsonl(human_path)
        env = make_env(
            game_id,
            mission_id,
            wrap_rewards=False,
            session_id=session_id,
            turbo=turbo,
        )
        frame_skip = int(_base_env(env).frame_skip)
        try:
            for seg in segments:
                seg_id = str(seg["id"])
                print(f"Recording {seg_id} frames {seg['frame_start']}..{seg['frame_end']}...")
                obs, actions = record_segment(
                    env,
                    human_by_frame,
                    seg,
                    max_steps=max_steps,
                )
                if obs.shape[0] == 0:
                    print(f"  skip {seg_id}: no transitions")
                    continue
                out = mission / "demos" / f"{seg_id}.npz"
                write_demo_npz(
                    out,
                    obs=obs,
                    actions=actions,
                    seg=seg,
                    mission_id=mission_id,
                    frame_skip=frame_skip,
                )
                print(
                    f"  wrote {out.name}: N={obs.shape[0]} "
                    f"obs=[{obs.min():.3f},{obs.max():.3f}]"
                )
                written.append(out)
        finally:
            env.close()
        return written

    prefix = session_id
    cleanup_bridge_sessions(f"{prefix}_")
    print(f"Parallel record: {len(segments)} segment(s), {n_workers} worker(s)", flush=True)
    try:
        with ProcessPoolExecutor(max_workers=n_workers) as pool:
            futures = {
                pool.submit(
                    _record_segment_job,
                    str(mission.resolve()),
                    game_id,
                    mission_id,
                    seg,
                    human_path_str=str(human_path.resolve()),
                    rank=i,
                    session_prefix=prefix,
                    turbo=turbo,
                    max_steps=max_steps,
                ): str(seg.get("id"))
                for i, seg in enumerate(segments)
            }
            for fut in as_completed(futures):
                seg_id = futures[fut]
                try:
                    result = fut.result()
                except Exception:
                    print(f"  failed {seg_id}")
                    raise
                if result is not None:
                    written.append(Path(result))
    finally:
        cleanup_bridge_sessions(f"{prefix}_")

    written.sort(key=lambda p: p.name)
    return written
