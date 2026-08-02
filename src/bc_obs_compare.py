"""Сравнение obs: NPZ demos_for_bc vs live env на human-траектории."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from bc_open_loop_eval import FrameAction, load_human_playthrough
from project_paths import mission_dir
from train.phase_heads import PolicyHeadsSpec, load_game_action_strings, predict_with_phase


@dataclass(frozen=True)
class ObsStepDiff:
    frame: int
    npz_index: int
    mae: float
    max_abs: float
    match_frac: float
    npz_mean: float
    live_mean: float


@dataclass(frozen=True)
class ObsCompareReport:
    segment_id: str
    frame_start: int
    frame_end: int
    n_compared: int
    mean_mae: float
    mean_match_frac: float
    first_diverge_frame: int | None
    steps: tuple[ObsStepDiff, ...]
    pred_agree_frac: float | None = None


def frame_to_npz_index(frame: int, *, frame_start: int, frame_skip: int) -> int:
    if (frame - frame_start) % frame_skip != 0:
        raise ValueError(f"frame {frame} is not a decision frame from {frame_start} skip {frame_skip}")
    return (frame - frame_start) // frame_skip


def load_npz_obs(npz_path: Path) -> tuple[np.ndarray, dict[str, Any]]:
    if not npz_path.is_file():
        raise FileNotFoundError(f"npz not found: {npz_path}")
    with np.load(npz_path, allow_pickle=True) as z:
        meta_raw = z["meta"]
        meta: dict[str, Any] = json.loads(str(meta_raw.item() if hasattr(meta_raw, "item") else meta_raw))
        obs = np.asarray(z["obs"], dtype=np.float32)
    return obs, meta


def _obs_diff(npz_obs: np.ndarray, live_obs: np.ndarray) -> ObsStepDiff:
    diff = np.abs(npz_obs.astype(np.float64) - live_obs.astype(np.float64))
    mae = float(diff.mean())
    max_abs = float(diff.max())
    match_frac = float((diff < 1.0 / 255.0).mean())
    return ObsStepDiff(
        frame=-1,
        npz_index=-1,
        mae=mae,
        max_abs=max_abs,
        match_frac=match_frac,
        npz_mean=float(npz_obs.mean()),
        live_mean=float(live_obs.mean()),
    )


def compare_obs_on_trajectory(
    env: Any,
    npz_obs: np.ndarray,
    human_frames: Sequence[FrameAction],
    *,
    frame_start: int,
    frame_skip: int = 4,
    save_state: str = "save_states/cp_gameplay0.fc0",
    model: Any | None = None,
    heads_spec: PolicyHeadsSpec | None = None,
    action_strings: Sequence[str] | None = None,
    mae_diverge_threshold: float = 0.01,
    replay_frames: Sequence[FrameAction] | None = None,
) -> ObsCompareReport:
    """Replay human actions в env; сравнить obs с NPZ на decision frames.

  ``human_frames`` — decision-кадры для сравнения; ``replay_frames`` — покадровая
  траектория (frame_skip=1). Если replay не задан, шагает только по human_frames.
    """
    decision_by_frame = {fa.frame: fa for fa in human_frames}
    trajectory = list(replay_frames) if replay_frames is not None else list(human_frames)
    obs, info = env.reset(options={"save_state": save_state})
    steps: list[ObsStepDiff] = []
    pred_agree = 0
    pred_total = 0
    first_diverge: int | None = None

    for fa in trajectory:
        decision = decision_by_frame.get(fa.frame)
        if decision is not None:
            live_obs = np.asarray(obs, dtype=np.float32)
            npz_idx = frame_to_npz_index(decision.frame, frame_start=frame_start, frame_skip=frame_skip)
            if npz_idx >= npz_obs.shape[0]:
                break
            npz_row = npz_obs[npz_idx]
            step = _obs_diff(npz_row, live_obs)
            step = ObsStepDiff(
                frame=decision.frame,
                npz_index=npz_idx,
                mae=step.mae,
                max_abs=step.max_abs,
                match_frac=step.match_frac,
                npz_mean=step.npz_mean,
                live_mean=step.live_mean,
            )
            steps.append(step)
            if first_diverge is None and step.mae > mae_diverge_threshold:
                first_diverge = decision.frame

            if model is not None and action_strings is not None:
                phase_id = info.get("phase_id")
                pred_npz, _, _ = predict_with_phase(
                    model, npz_row[np.newaxis, ...], phase_id, heads_spec, deterministic=True
                )
                pred_live, _, _ = predict_with_phase(
                    model, live_obs[np.newaxis, ...], phase_id, heads_spec, deterministic=True
                )
                pi = int(pred_npz[0]) if hasattr(pred_npz, "__len__") else int(pred_npz)
                pl = int(pred_live[0]) if hasattr(pred_live, "__len__") else int(pred_live)
                pred_total += 1
                pred_agree += int(pi == pl)

        obs, _r, term, trunc, info = env.step(fa.action_index)
        if term or trunc:
            break

    if not steps:
        return ObsCompareReport(
            segment_id="",
            frame_start=frame_start,
            frame_end=human_frames[-1].frame if human_frames else frame_start,
            n_compared=0,
            mean_mae=0.0,
            mean_match_frac=0.0,
            first_diverge_frame=None,
            steps=(),
        )

    mean_mae = sum(s.mae for s in steps) / len(steps)
    mean_match = sum(s.match_frac for s in steps) / len(steps)
    return ObsCompareReport(
        segment_id="",
        frame_start=frame_start,
        frame_end=steps[-1].frame,
        n_compared=len(steps),
        mean_mae=mean_mae,
        mean_match_frac=mean_match,
        first_diverge_frame=first_diverge,
        steps=tuple(steps),
        pred_agree_frac=(pred_agree / pred_total) if pred_total else None,
    )


def write_obs_compare_report(path: Path, report: ObsCompareReport, *, segment_id: str = "") -> None:
    lines = [
        "# BC obs compare: NPZ vs live env",
        "",
        f"segment: {segment_id or report.segment_id or 'seg_*'}",
        f"frames: {report.frame_start}–{report.frame_end} ({report.n_compared} steps)",
        f"mean MAE: {report.mean_mae:.6f}",
        f"mean pixel match (<1/255): {report.mean_match_frac:.4f}",
        f"first diverge (MAE>0.01): {report.first_diverge_frame}",
    ]
    if report.pred_agree_frac is not None:
        lines.append(f"model pred agree (NPZ obs vs live obs): {report.pred_agree_frac:.1%}")
    if report.mean_mae > 0.05:
        lines += [
            "",
            "## Likely root cause",
            "",
            "Систематический разрыв с кадра 1034: save state ≠ FM2, или replay шёл "
            "с frame_skip>1 (нужна покадровая траектория). Также проверьте "
            "`gd_to_raw_gray` в demos_for_bc.lua vs bridge.lua.",
            "",
            "Фикс: унифицировать `gd_to_raw_gray` в обоих lua; переснять `demos_for_bc/seg_*.npz`.",
        ]
    lines += [
        "",
        "## Per-step (worst 15 by MAE)",
        "",
        "| frame | npz_idx | MAE | max | match_frac | npz_mean | live_mean |",
        "|-------|---------|-----|-----|------------|----------|-----------|",
    ]
    worst = sorted(report.steps, key=lambda s: s.mae, reverse=True)[:15]
    for s in worst:
        lines.append(
            f"| {s.frame} | {s.npz_index} | {s.mae:.6f} | {s.max_abs:.4f} | "
            f"{s.match_frac:.4f} | {s.npz_mean:.4f} | {s.live_mean:.4f} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_obs_compare(
    game_id: str,
    mission_id: str,
    *,
    segment_id: str = "seg_002",
    frame_start: int = 1034,
    frame_end: int = 1300,
    frame_skip: int = 4,
    model_path: Path | None = None,
    out_dir: Path | None = None,
) -> ObsCompareReport:
    from env.loader import make_env
    from train.env_factory import cleanup_bridge_sessions
    from train.phase_aware_ppo import PhaseAwarePPO

    mission = mission_dir(game_id, mission_id)
    npz_path = mission / "reference" / "demos_for_bc" / f"{segment_id}.npz"
    npz_obs, meta = load_npz_obs(npz_path)
    seg_start = int(meta.get("frame_start", frame_start))
    skip = int(meta.get("frame_skip", frame_skip))
    action_strings = load_game_action_strings(game_id)
    human_frames = load_human_playthrough(
        mission,
        frame_start=frame_start,
        frame_end=frame_end,
        frame_skip=frame_skip,
        action_strings=action_strings,
    )
    replay_frames = load_human_playthrough(
        mission,
        frame_start=frame_start,
        frame_end=frame_end,
        frame_skip=1,
        action_strings=action_strings,
    )

    model = None
    heads_spec = None
    if model_path is not None:
        from train.phase_heads import load_policy_heads_spec

        heads_spec = load_policy_heads_spec(game_id)
        model = PhaseAwarePPO.load(str(model_path.with_suffix("")), device="cpu")
        model.heads_spec = heads_spec

    cleanup_bridge_sessions(prefix="bench_")
    env = make_env(
        game_id,
        mission_id,
        session_id="bench_obs_compare",
        save_state="save_states/cp_gameplay0.fc0",
        turbo=True,
        show_window=False,
        frame_skip=1,
    )
    try:
        report = compare_obs_on_trajectory(
            env,
            npz_obs,
            human_frames,
            frame_start=seg_start,
            frame_skip=skip,
            model=model,
            heads_spec=heads_spec,
            action_strings=action_strings,
            replay_frames=replay_frames,
        )
    finally:
        env.close()
        cleanup_bridge_sessions(prefix="bench_")

    report = ObsCompareReport(
        segment_id=segment_id,
        frame_start=report.frame_start,
        frame_end=report.frame_end,
        n_compared=report.n_compared,
        mean_mae=report.mean_mae,
        mean_match_frac=report.mean_match_frac,
        first_diverge_frame=report.first_diverge_frame,
        steps=report.steps,
        pred_agree_frac=report.pred_agree_frac,
    )

    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        write_obs_compare_report(out_dir / "obs_compare_report.md", report, segment_id=segment_id)

    return report
