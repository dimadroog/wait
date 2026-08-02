"""BC open-loop / closed-loop диагностика: match на human-траектории vs agent logs."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np

from project_paths import mission_dir
from train.action_map import action_string_to_index
from train.phase_heads import PolicyHeadsSpec, load_game_action_strings, predict_with_phase


@dataclass(frozen=True)
class FrameAction:
    frame: int
    action: str
    action_index: int


@dataclass(frozen=True)
class MatchStats:
    correct: int
    total: int
    noop_correct: int
    noop_total: int
    move_correct: int
    move_total: int
    b_correct: int = 0
    b_total: int = 0
    attack_window_correct: int = 0
    attack_window_total: int = 0
    attack_window_b_correct: int = 0
    attack_window_b_total: int = 0

    @property
    def pct(self) -> float:
        return 100.0 * self.correct / max(self.total, 1)

    @property
    def noop_pct(self) -> float:
        return 100.0 * self.noop_correct / max(self.noop_total, 1)

    @property
    def move_pct(self) -> float:
        return 100.0 * self.move_correct / max(self.move_total, 1)

    @property
    def b_pct(self) -> float:
        return 100.0 * self.b_correct / max(self.b_total, 1)

    @property
    def attack_window_pct(self) -> float:
        return 100.0 * self.attack_window_correct / max(self.attack_window_total, 1)

    @property
    def attack_window_b_pct(self) -> float:
        return 100.0 * self.attack_window_b_correct / max(self.attack_window_b_total, 1)


@dataclass
class AttackWindowRow:
    frame: int
    human_action: str
    open_loop_pred: str | None = None
    closed_loop_pred: str | None = None
    phase_id: str | None = None
    head_id: str | None = None
    open_match: bool | None = None
    closed_match: bool | None = None


@dataclass(frozen=True)
class OpenLoopReport:
    stats: MatchStats
    attack_rows: tuple[AttackWindowRow, ...]
    frame_start: int
    frame_end: int
    attack_window: tuple[int, int]


@dataclass(frozen=True)
class ClosedLoopReport:
    stats: MatchStats
    attack_rows: tuple[AttackWindowRow, ...]
    episode: int
    frame_start: int
    frame_end: int
    attack_window: tuple[int, int]


@dataclass(frozen=True)
class NpzOfflineReport:
    segment_id: str
    stats: MatchStats


@dataclass(frozen=True)
class TransferVerdict:
    label: str
    rules_triggered: tuple[str, ...]
    details: str


def _buttons(action: str) -> frozenset[str]:
    s = (action or "").strip()
    if not s:
        return frozenset()
    return frozenset(s.split("+"))


def is_b_action(action: str) -> bool:
    return "B" in _buttons(action)


def action_index_to_string(index: int, action_strings: Sequence[str]) -> str:
    if 0 <= index < len(action_strings):
        return str(action_strings[index])
    return ""


def parse_attack_window(spec: str) -> tuple[int, int]:
    raw = spec.strip()
    if "-" not in raw:
        raise ValueError(f"attack window must be START-END, got {spec!r}")
    start_s, end_s = raw.split("-", 1)
    start, end = int(start_s), int(end_s)
    if end < start:
        raise ValueError(f"attack window end < start: {spec!r}")
    return start, end


def default_human_playthrough_path(mission: Path) -> Path:
    return mission / "reference" / "human_playthrough.jsonl"


def resolve_save_state_start_frame(mission: Path, save_state: str) -> int:
    """Кадр FM2, соответствующий save state (для warmup replay до frame_start)."""
    from playthrough_build import load_head_save_states

    stem = Path(save_state).stem
    heads = load_head_save_states(mission)
    for entries in (heads or {}).values():
        for entry in entries:
            if str(entry.get("id")) == stem and entry.get("frame") is not None:
                return int(entry["frame"])

    from inference_states import gameplay_start_frame

    gp = gameplay_start_frame(mission)
    if gp is not None:
        return int(gp)
    raise ValueError(f"cannot resolve start frame for save state: {save_state}")


def build_open_loop_replay_frames(
    mission: Path,
    *,
    frame_end: int,
    save_state: str,
    action_strings: Sequence[str],
    human_path: Path | None = None,
) -> list[FrameAction]:
    """Покадровая human-траектория от save state до frame_end (warmup + eval)."""
    replay_start = resolve_save_state_start_frame(mission, save_state)
    return load_human_playthrough(
        mission,
        frame_start=replay_start,
        frame_end=frame_end,
        frame_skip=1,
        action_strings=action_strings,
        human_path=human_path,
    )


def is_decision_frame(frame: int, *, frame_start: int, decision_frame_skip: int) -> bool:
    return (int(frame) - int(frame_start)) % int(decision_frame_skip) == 0


def load_human_playthrough(
    mission: Path,
    *,
    frame_start: int,
    frame_end: int,
    frame_skip: int = 4,
    action_strings: Sequence[str] | None = None,
    human_path: Path | None = None,
) -> list[FrameAction]:
    """Human frames; при frame_skip>1 — только decision-кадры: (frame - frame_start) % skip == 0."""
    path = human_path if human_path is not None else default_human_playthrough_path(mission)
    if not path.is_file():
        raise FileNotFoundError(f"human playthrough not found: {path}")
    if action_strings is None:
        game_id = mission.parent.parent.name
        action_strings = load_game_action_strings(game_id)

    out: list[FrameAction] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            frame = int(row["frame"])
            if frame < frame_start or frame > frame_end:
                continue
            if (frame - frame_start) % frame_skip != 0:
                continue
            action = str(row.get("action", "") or "")
            out.append(
                FrameAction(
                    frame=frame,
                    action=action,
                    action_index=action_string_to_index(action, action_strings),
                )
            )
    out.sort(key=lambda fa: fa.frame)
    return out


def load_human_actions_by_frame(
    *,
    frame_start: int,
    frame_end: int,
    human_path: Path,
) -> dict[int, str]:
    path = human_path
    if not path.is_file():
        raise FileNotFoundError(f"human playthrough not found: {path}")
    out: dict[int, str] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            frame = int(row["frame"])
            if frame_start <= frame <= frame_end:
                out[frame] = str(row.get("action", "") or "")
    return out


def _normalize_action_index(action: Any) -> int:
    if isinstance(action, np.ndarray):
        return int(action.item() if action.ndim == 0 else action[0])
    if isinstance(action, (list, tuple)):
        return int(action[0])
    return int(action)


def _empty_stats() -> MatchStats:
    return MatchStats(0, 0, 0, 0, 0, 0)


def update_match_stats(
    stats: MatchStats,
    *,
    pred_index: int,
    human_index: int,
    human_action: str,
    action_strings: Sequence[str],
    noop_action_index: int,
    frame: int,
    attack_window: tuple[int, int],
) -> MatchStats:
    match = int(pred_index == human_index)
    is_noop = human_index == noop_action_index
    human_is_b = is_b_action(human_action)
    in_window = attack_window[0] <= frame <= attack_window[1]

    return MatchStats(
        correct=stats.correct + match,
        total=stats.total + 1,
        noop_correct=stats.noop_correct + (match if is_noop else 0),
        noop_total=stats.noop_total + (1 if is_noop else 0),
        move_correct=stats.move_correct + (match if not is_noop else 0),
        move_total=stats.move_total + (0 if is_noop else 1),
        b_correct=stats.b_correct + (match if human_is_b else 0),
        b_total=stats.b_total + (1 if human_is_b else 0),
        attack_window_correct=stats.attack_window_correct + (match if in_window else 0),
        attack_window_total=stats.attack_window_total + (1 if in_window else 0),
        attack_window_b_correct=stats.attack_window_b_correct
        + (match if in_window and human_is_b else 0),
        attack_window_b_total=stats.attack_window_b_total
        + (1 if in_window and human_is_b else 0),
    )


def _current_frame(info: dict[str, Any]) -> int:
    return int((info.get("ram") or {}).get("frame", 0))


def _build_attack_table_rows(
    *,
    attack_table_frames: Sequence[int],
    attack_row_map: dict[int, AttackWindowRow],
    human_by_frame: dict[int, str],
    agent_by_frame: dict[int, str] | None = None,
) -> tuple[AttackWindowRow, ...]:
    attack_rows: list[AttackWindowRow] = []
    for frame in attack_table_frames:
        if frame in attack_row_map:
            attack_rows.append(attack_row_map[frame])
            continue
        human_action = human_by_frame.get(frame, "")
        closed = (agent_by_frame or {}).get(frame)
        attack_rows.append(
            AttackWindowRow(
                frame=frame,
                human_action=human_action,
                closed_loop_pred=closed,
            )
        )
    return tuple(attack_rows)


def evaluate_open_loop(
    model: Any,
    env: Any,
    heads_spec: PolicyHeadsSpec | None,
    human_frames: Sequence[FrameAction],
    action_strings: Sequence[str],
    *,
    save_state: str = "save_states/cp_gameplay0.fc0",
    attack_window: tuple[int, int] = (1195, 1210),
    deterministic: bool = True,
    noop_action_index: int = 0,
    attack_table_frames: tuple[int, ...] = (1199, 1200, 1201, 1202, 1203, 1204, 1205),
    human_path: Path | None = None,
    replay_frames: Sequence[FrameAction] | None = None,
    on_decision: Callable[[FrameAction, str, str, bool], None] | None = None,
) -> OpenLoopReport:
    if not human_frames:
        return OpenLoopReport(
            stats=_empty_stats(),
            attack_rows=(),
            frame_start=0,
            frame_end=0,
            attack_window=attack_window,
        )

    decision_by_frame = {fa.frame: fa for fa in human_frames}
    trajectory = list(replay_frames) if replay_frames is not None else list(human_frames)
    if not trajectory:
        raise ValueError("open-loop replay trajectory is empty")

    obs, info = env.reset(options={"save_state": save_state})
    stats = _empty_stats()
    attack_row_map: dict[int, AttackWindowRow] = {}

    for fa in trajectory:
        current = _current_frame(info)
        if current != fa.frame:
            raise RuntimeError(
                f"open-loop frame drift: expected {fa.frame}, env at {current}; "
                "check frame_start/frame_skip alignment"
            )

        decision = decision_by_frame.get(fa.frame)
        if decision is not None:
            phase_id = info.get("phase_id")
            pred_raw, _, head_id = predict_with_phase(
                model, obs, phase_id, heads_spec, deterministic=deterministic
            )
            pred_index = _normalize_action_index(pred_raw)
            pred_action = action_index_to_string(pred_index, action_strings)

            stats = update_match_stats(
                stats,
                pred_index=pred_index,
                human_index=decision.action_index,
                human_action=decision.action,
                action_strings=action_strings,
                noop_action_index=noop_action_index,
                frame=decision.frame,
                attack_window=attack_window,
            )

            if decision.frame in attack_table_frames:
                attack_row_map[decision.frame] = AttackWindowRow(
                    frame=decision.frame,
                    human_action=decision.action,
                    open_loop_pred=pred_action,
                    phase_id=str(phase_id) if phase_id is not None else None,
                    head_id=head_id,
                    open_match=bool(pred_index == decision.action_index),
                )

            if on_decision is not None:
                on_decision(
                    decision,
                    pred_action,
                    decision.action,
                    bool(pred_index == decision.action_index),
                )

        obs, _reward, terminated, truncated, info = env.step(fa.action_index)
        if terminated or truncated:
            break

    human_by_frame = {fa.frame: fa.action for fa in human_frames}
    if human_path is not None and attack_table_frames:
        full_human = load_human_actions_by_frame(
            frame_start=min(attack_table_frames),
            frame_end=max(attack_table_frames),
            human_path=human_path,
        )
        human_by_frame.update(full_human)

    return OpenLoopReport(
        stats=stats,
        attack_rows=_build_attack_table_rows(
            attack_table_frames=attack_table_frames,
            attack_row_map=attack_row_map,
            human_by_frame=human_by_frame,
        ),
        frame_start=human_frames[0].frame,
        frame_end=human_frames[-1].frame,
        attack_window=attack_window,
    )


def load_inference_actions_by_frame(
    inference_path: Path,
    *,
    frame_start: int,
    frame_end: int,
    episode: int | None = 1,
) -> tuple[dict[int, str], int]:
    if not inference_path.is_file():
        raise FileNotFoundError(f"inference log not found: {inference_path}")

    by_episode: dict[int, dict[int, str]] = {}
    with inference_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            ep = int(row.get("episode", 0))
            frame = int(row["frame"])
            if frame < frame_start or frame > frame_end:
                continue
            by_episode.setdefault(ep, {})[frame] = str(row.get("action", "") or "")

    if not by_episode:
        return {}, 0

    if episode is not None and episode in by_episode:
        return by_episode[episode], episode

    chosen_ep = min(by_episode)
    return by_episode[chosen_ep], chosen_ep


def evaluate_closed_loop_from_logs(
    inference_inputs_path: Path,
    human_path: Path,
    action_strings: Sequence[str],
    *,
    frame_start: int,
    frame_end: int,
    frame_skip: int = 4,
    attack_window: tuple[int, int] = (1195, 1210),
    episode: int | None = 1,
    noop_action_index: int = 0,
    attack_table_frames: tuple[int, ...] = (1199, 1200, 1201, 1202, 1203, 1204, 1205),
) -> ClosedLoopReport:
    agent_by_frame, chosen_ep = load_inference_actions_by_frame(
        inference_inputs_path,
        frame_start=frame_start,
        frame_end=frame_end,
        episode=episode,
    )
    human_by_frame = load_human_actions_by_frame(
        frame_start=frame_start,
        frame_end=frame_end,
        human_path=human_path,
    )

    stats = _empty_stats()
    attack_row_map: dict[int, AttackWindowRow] = {}

    for frame in sorted(set(agent_by_frame) & set(human_by_frame)):
        if (frame - frame_start) % frame_skip != 0:
            continue
        human_action = human_by_frame[frame]
        agent_action = agent_by_frame[frame]
        human_index = action_string_to_index(human_action, action_strings)
        pred_index = action_string_to_index(agent_action, action_strings)

        stats = update_match_stats(
            stats,
            pred_index=pred_index,
            human_index=human_index,
            human_action=human_action,
            action_strings=action_strings,
            noop_action_index=noop_action_index,
            frame=frame,
            attack_window=attack_window,
        )

        if frame in attack_table_frames:
            attack_row_map[frame] = AttackWindowRow(
                frame=frame,
                human_action=human_action,
                closed_loop_pred=agent_action,
                closed_match=bool(pred_index == human_index),
            )

    attack_rows = _build_attack_table_rows(
        attack_table_frames=attack_table_frames,
        attack_row_map=attack_row_map,
        human_by_frame=human_by_frame,
        agent_by_frame=agent_by_frame,
    )

    return ClosedLoopReport(
        stats=stats,
        attack_rows=attack_rows,
        episode=chosen_ep,
        frame_start=frame_start,
        frame_end=frame_end,
        attack_window=attack_window,
    )


def evaluate_npz_offline(
    model: Any,
    mission: Path,
    heads_spec: PolicyHeadsSpec | None,
    action_strings: Sequence[str],
    *,
    segment_id: str = "seg_002",
    noop_action_index: int = 0,
) -> NpzOfflineReport:
    """Greedy match на obs из reference/demos_for_bc (без FCEUX)."""
    from train.bc_pretrain import bc_demo_action_match_rate, load_demo_dataset

    demo_path = mission / "reference" / "demos_for_bc" / f"{segment_id}.npz"
    if not demo_path.is_file():
        raise FileNotFoundError(f"demo npz not found: {demo_path}")

    bc_stats = bc_demo_action_match_rate(
        model, mission, heads_spec=heads_spec, demo_paths=[demo_path]
    )
    batch = load_demo_dataset(
        mission,
        demo_paths=[demo_path],
        require_quality_pass=True,
        heads_spec=heads_spec,
        action_strings=action_strings,
    )
    b_correct = b_total = 0
    if batch is not None:
        from train.bc_pretrain import _bc_logits
        from train.multi_head_policy import MultiHeadActorCriticPolicy
        import torch
        from stable_baselines3.common.policies import ActorCriticCnnPolicy

        policy = model.policy
        assert isinstance(policy, ActorCriticCnnPolicy)
        policy.set_training_mode(False)
        n = int(batch.actions.shape[0])
        with torch.no_grad():
            for start in range(0, n, 256):
                end = min(start + 256, n)
                obs_t = torch.as_tensor(batch.obs[start:end], dtype=torch.float32)
                act_np = batch.actions[start:end]
                head_t = None
                if batch.head_indices is not None:
                    head_t = torch.as_tensor(batch.head_indices[start:end], dtype=torch.long)
                logits = _bc_logits(policy, obs_t, head_t)
                pred = logits.argmax(dim=-1).cpu().numpy()
                valid_slice = batch.valid_mask[start:end] if batch.valid_mask is not None else None
                for i, (p, a) in enumerate(zip(pred, act_np, strict=True)):
                    if valid_slice is not None and not bool(valid_slice[i]):
                        continue
                    action_str = action_index_to_string(int(a), action_strings)
                    if is_b_action(action_str):
                        b_total += 1
                        b_correct += int(int(p) == int(a))
        if isinstance(policy, MultiHeadActorCriticPolicy):
            policy.clear_batch_heads()

    stats = MatchStats(
        correct=bc_stats.correct,
        total=bc_stats.total,
        noop_correct=bc_stats.noop_correct,
        noop_total=bc_stats.noop_total,
        move_correct=bc_stats.move_correct,
        move_total=bc_stats.move_total,
        b_correct=b_correct,
        b_total=b_total,
    )
    return NpzOfflineReport(segment_id=segment_id, stats=stats)


def build_transfer_verdict(
    open_loop: OpenLoopReport | None,
    closed_loop: ClosedLoopReport | None,
    *,
    npz_offline: NpzOfflineReport | None = None,
    attack_window_intro_phases: Sequence[str] | None = None,
) -> TransferVerdict:
    rules: list[str] = []
    intro_phases = set(attack_window_intro_phases or ("intro", "title"))

    if open_loop is not None:
        for row in open_loop.attack_rows:
            if row.phase_id in intro_phases:
                rules.append("phase_bug_intro_on_attack_window")
                break

    open_b = open_loop.stats.b_pct if open_loop is not None else None
    closed_b = closed_loop.stats.attack_window_b_pct if closed_loop is not None else None
    open_total = open_loop.stats.pct if open_loop is not None else None
    closed_total = closed_loop.stats.pct if closed_loop is not None else None
    npz_total = npz_offline.stats.pct if npz_offline is not None else None
    npz_b = npz_offline.stats.b_pct if npz_offline is not None else None

    if (
        npz_total is not None
        and npz_total >= 80.0
        and open_total is not None
        and open_total < 60.0
    ):
        rules.append("obs_pipeline_mismatch")

    if open_b is not None and open_b >= 80.0 and closed_b is not None and closed_b < 30.0:
        rules.append("trajectory_drift")

    if open_b is not None and open_b < 50.0 and "obs_pipeline_mismatch" not in rules:
        rules.append("bc_obs_head")

    if (
        open_total is not None
        and open_total >= 90.0
        and closed_total is not None
        and closed_total < 50.0
    ):
        rules.append("distribution_shift")

    if "phase_bug_intro_on_attack_window" in rules:
        label = "PHASE_BUG"
        details = "На attack-window активна intro/title голова (только noop)."
    elif "obs_pipeline_mismatch" in rules:
        label = "OBS_PIPELINE_MISMATCH"
        npz_seg = npz_offline.segment_id if npz_offline is not None else "seg_*"
        details = (
            f"NPZ offline ({npz_seg}) {npz_total:.1f}% при live open-loop {open_total:.1f}% — "
            "obs в env ≠ записанные демо (или phase/head при live step)."
        )
    elif "trajectory_drift" in rules:
        label = "TRAJECTORY_DRIFT"
        details = (
            "BC учит B на human path (open-loop), но closed-loop не копирует — "
            "вероятен дрейф траектории."
        )
    elif "bc_obs_head" in rules:
        label = "BC_OBS_HEAD"
        details = "Attack-кадры не выучены даже на human path — проблема в obs/голове/данных."
    elif "distribution_shift" in rules:
        label = "DISTRIBUTION_SHIFT"
        details = "Высокий open-loop match при низком closed-loop — сдвиг распределения."
    elif open_loop is not None and closed_loop is not None:
        label = "INCONCLUSIVE"
        details = "Пороги вердикта не сработали; см. отчёты по метрикам."
    elif open_loop is not None:
        label = "OPEN_LOOP_ONLY"
        details = "Только open-loop отчёт (без closed-loop логов)."
    elif closed_loop is not None:
        label = "CLOSED_LOOP_ONLY"
        details = "Только closed-loop отчёт (без FCEUX open-loop)."
    else:
        label = "NO_DATA"
        details = "Нет данных для вердикта."

    return TransferVerdict(label=label, rules_triggered=tuple(rules), details=details)


def _format_stats_table(stats: MatchStats) -> list[str]:
    return [
        "| metric | value |",
        "|--------|-------|",
        f"| total | {stats.correct}/{stats.total} ({stats.pct:.1f}%) |",
        f"| noop | {stats.noop_correct}/{stats.noop_total} ({stats.noop_pct:.1f}%) |",
        f"| move | {stats.move_correct}/{stats.move_total} ({stats.move_pct:.1f}%) |",
        f"| B-only | {stats.b_correct}/{stats.b_total} ({stats.b_pct:.1f}%) |",
        f"| attack window | {stats.attack_window_correct}/{stats.attack_window_total} "
        f"({stats.attack_window_pct:.1f}%) |",
        f"| attack window B | {stats.attack_window_b_correct}/{stats.attack_window_b_total} "
        f"({stats.attack_window_b_pct:.1f}%) |",
    ]


def _format_action(action: str | None) -> str:
    if action is None:
        return "—"
    return "(noop)" if action == "" else action


def _format_attack_table(rows: Sequence[AttackWindowRow]) -> list[str]:
    lines = [
        "| frame | human | open-loop | closed-loop | phase | head |",
        "|-------|-------|-----------|-------------|-------|------|",
    ]
    for row in rows:
        lines.append(
            f"| {row.frame} | {_format_action(row.human_action)} | "
            f"{_format_action(row.open_loop_pred)} | {_format_action(row.closed_loop_pred)} | "
            f"{row.phase_id or '—'} | {row.head_id or '—'} |"
        )
    return lines


def write_open_loop_report(path: Path, report: OpenLoopReport, *, model_path: str = "") -> None:
    lines = [
        "# BC open-loop report",
        "",
        f"frames: {report.frame_start}–{report.frame_end}",
        f"attack window: {report.attack_window[0]}–{report.attack_window[1]}",
    ]
    if model_path:
        lines.append(f"model: `{model_path}`")
    lines += ["", "## Match stats", ""] + _format_stats_table(report.stats)
    lines += ["", "## Attack window detail", ""] + _format_attack_table(report.attack_rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_closed_loop_report(
    path: Path,
    report: ClosedLoopReport,
    *,
    inference_path: str = "",
) -> None:
    lines = [
        "# BC closed-loop report",
        "",
        f"episode: {report.episode}",
        f"frames: {report.frame_start}–{report.frame_end}",
        f"attack window: {report.attack_window[0]}–{report.attack_window[1]}",
    ]
    if inference_path:
        lines.append(f"inference log: `{inference_path}`")
    lines += ["", "## Match stats", ""] + _format_stats_table(report.stats)
    lines += ["", "## Attack window detail", ""] + _format_attack_table(report.attack_rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_npz_offline_report(path: Path, report: NpzOfflineReport) -> None:
    lines = [
        "# BC NPZ offline report",
        "",
        f"segment: {report.segment_id}",
        "",
        "## Match stats",
        "",
    ] + _format_stats_table(report.stats)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_transfer_verdict(
    path: Path,
    verdict: TransferVerdict,
    *,
    run_label: str = "",
    open_loop: OpenLoopReport | None = None,
    closed_loop: ClosedLoopReport | None = None,
    npz_offline: NpzOfflineReport | None = None,
) -> None:
    lines = ["# BC transfer verdict", ""]
    if run_label:
        lines.append(f"run: **{run_label}**")
    lines.append(f"verdict: **{verdict.label}**")
    lines.append("")
    lines.append(verdict.details)
    lines.append("")
    if verdict.rules_triggered:
        lines.append("rules: " + ", ".join(verdict.rules_triggered))
        lines.append("")

    lines += [
        "## Verdict matrix (reference)",
        "",
        "| Open-loop B | Closed-loop attack B | Conclusion |",
        "|-------------|------------------------|------------|",
        "| >= 80% | < 30% | Trajectory drift |",
        "| < 50% | any | BC/obs/head |",
        "| total >= 90% | total < 50% | Distribution shift |",
        "| NPZ offline >= 80%, live open-loop < 60% | — | Obs pipeline mismatch |",
        "| phase=intro on attack window | — | Phase bug |",
        "",
    ]

    if npz_offline is not None:
        lines += [
            "## NPZ offline summary",
            "",
            f"- segment: {npz_offline.segment_id}",
            f"- total: {npz_offline.stats.pct:.1f}%",
            f"- B: {npz_offline.stats.b_pct:.1f}%",
            "",
        ]
    if open_loop is not None:
        lines += [
            "## Open-loop summary",
            "",
            f"- total: {open_loop.stats.pct:.1f}%",
            f"- B: {open_loop.stats.b_pct:.1f}%",
            "",
        ]
    if closed_loop is not None:
        lines += [
            "## Closed-loop summary",
            "",
            f"- total: {closed_loop.stats.pct:.1f}%",
            f"- attack window B: {closed_loop.stats.attack_window_b_pct:.1f}%",
            "",
        ]

    if open_loop is not None and closed_loop is not None:
        merged_rows: dict[int, AttackWindowRow] = {}
        for row in open_loop.attack_rows:
            merged_rows[row.frame] = AttackWindowRow(
                frame=row.frame,
                human_action=row.human_action,
                open_loop_pred=row.open_loop_pred,
                phase_id=row.phase_id,
                head_id=row.head_id,
                open_match=row.open_match,
            )
        for row in closed_loop.attack_rows:
            existing = merged_rows.get(row.frame)
            if existing is None:
                merged_rows[row.frame] = row
            else:
                existing.closed_loop_pred = row.closed_loop_pred
                existing.closed_match = row.closed_match
        lines += ["## Attack window (1199–1205)", ""] + _format_attack_table(
            [merged_rows[f] for f in sorted(merged_rows)]
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_reports(
    out_dir: Path,
    *,
    open_loop: OpenLoopReport | None = None,
    closed_loop: ClosedLoopReport | None = None,
    npz_offline: NpzOfflineReport | None = None,
    verdict: TransferVerdict | None = None,
    model_path: str = "",
    inference_path: str = "",
    run_label: str = "",
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    if npz_offline is not None:
        p = out_dir / "npz_offline_report.md"
        write_npz_offline_report(p, npz_offline)
        written["npz_offline"] = p

    if open_loop is not None:
        p = out_dir / "open_loop_report.md"
        write_open_loop_report(p, open_loop, model_path=model_path)
        written["open_loop"] = p

    if closed_loop is not None:
        p = out_dir / "closed_loop_report.md"
        write_closed_loop_report(p, closed_loop, inference_path=inference_path)
        written["closed_loop"] = p

    if verdict is not None:
        p = out_dir / "bc_transfer_verdict.md"
        write_transfer_verdict(
            p,
            verdict,
            run_label=run_label,
            open_loop=open_loop,
            closed_loop=closed_loop,
            npz_offline=npz_offline,
        )
        written["verdict"] = p

    return written


def resolve_mission_paths(game_id: str, mission_id: str) -> Path:
    return mission_dir(game_id, mission_id)
