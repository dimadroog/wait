"""Оценка achievements по logs/YYYYMMDD_attempts.jsonl."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from log_utils import RETENTION_HOURS, load_jsonl_window
from project_paths import load_yaml, repo_root


def load_achievements_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or repo_root() / "config" / "achievements.yaml"
    return load_yaml(cfg_path)


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _nomination_by_slug(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {n["slug"]: n for n in config.get("nominations") or []}


def _matches_instant(record: dict[str, Any], condition: dict[str, Any]) -> bool:
    if "mission_clear" in condition and bool(record.get("mission_clear")) != bool(condition["mission_clear"]):
        return False
    if "died" in condition and bool(record.get("died")) != bool(condition["died"]):
        return False
    if "death_room" in condition and str(record.get("death_room", "")).upper() != str(condition["death_room"]).upper():
        return False
    if "max_episode_frames" in condition and int(record.get("episode_frames", 999)) > int(condition["max_episode_frames"]):
        return False
    if "min_achieved_checkpoints" in condition:
        if len(record.get("achieved_checkpoints") or []) < int(condition["min_achieved_checkpoints"]):
            return False
    if "min_max_checkpoint" in condition:
        if int(record.get("max_checkpoint", -1)) < int(condition["min_max_checkpoint"]):
            return False
    return True


def _death_key(record: dict[str, Any]) -> tuple[str, int] | None:
    if not record.get("died"):
        return None
    room = str(record.get("death_room") or "")
    bucket = record.get("death_x_bucket")
    if bucket is None:
        dx = record.get("death_x")
        bucket = int(dx) // 16 if dx is not None else None
    if bucket is None:
        return None
    return room, int(bucket)


def evaluate_records(
    records: list[dict[str, Any]],
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Вернуть копии записей с заполненным tags[]."""
    cfg = config or load_achievements_config()
    noms = _nomination_by_slug(cfg)
    out = [dict(r) for r in records]

    # instant rules
    for record in out:
        tags: list[str] = []
        for nom in cfg.get("nominations") or []:
            if nom.get("type") != "instant":
                continue
            if _matches_instant(record, nom.get("condition") or {}):
                tags.append(nom["slug"])
        record["tags"] = tags

    # death_cluster (deja_vu)
    deja_nom = noms.get("deja_vu")
    if deja_nom:
        min_count = int(deja_nom.get("min_count", 3))
        counts: Counter[tuple[str, int]] = Counter()
        for record in out:
            key = _death_key(record)
            if key:
                counts[key] += 1
        for record in out:
            key = _death_key(record)
            if key and counts[key] >= min_count and "deja_vu" not in record["tags"]:
                record["tags"].append("deja_vu")

    # new_record: новый max_checkpoint для model_version в окне retention
    if noms.get("new_record"):
        best_by_model: dict[str, int] = defaultdict(lambda: -1)
        ordered = sorted(
            out,
            key=lambda r: _parse_ts(r.get("timestamp"))
            or datetime.min.replace(tzinfo=timezone.utc),
        )
        for record in ordered:
            mv = str(record.get("model_version", ""))
            cp = int(record.get("max_checkpoint", -1))
            if cp > best_by_model[mv]:
                if best_by_model[mv] >= 0 and "new_record" not in record["tags"]:
                    record["tags"].append("new_record")
                best_by_model[mv] = cp

    # top_k episode_reward
    top_nom = noms.get("episode_reward")
    if top_nom:
        k = int(top_nom.get("k", 3))
        field = str(top_nom.get("field", "episode_reward"))
        ranked = sorted(out, key=lambda r: float(r.get(field, 0)), reverse=True)
        top_ids = {id(r) for r in ranked[:k]}
        for record in out:
            if id(record) in top_ids and "episode_reward" not in record["tags"]:
                record["tags"].append("episode_reward")

    return out


def evaluate_attempts_file(
    attempts_path: Path,
    *,
    hours: float = RETENTION_HOURS,
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    records = load_jsonl_window(attempts_path, hours=hours)
    return evaluate_records(records, config)


def write_tagged_attempts(attempts_path: Path, records: list[dict[str, Any]]) -> None:
    """Перезаписать файл только строками из retention-окна."""
    with attempts_path.open("w", encoding="utf-8") as f:
        for row in records:
            f.write(__import__("json").dumps(row, ensure_ascii=False) + "\n")


def tier_for_slug(slug: str, config: dict[str, Any] | None = None) -> str:
    cfg = config or load_achievements_config()
    for nom in cfg.get("nominations") or []:
        if nom.get("slug") == slug:
            return str(nom.get("tier", "gold"))
    return "gold"


def overlay_payload(
    record: dict[str, Any],
    *,
    config: dict[str, Any] | None = None,
    show_frames: int = 180,
) -> dict[str, Any]:
    """JSON для tmp/bridge/inference/overlay.json."""
    cfg = config or load_achievements_config()
    noms = _nomination_by_slug(cfg)
    achievements = []
    for slug in record.get("tags") or []:
        nom = noms.get(slug, {})
        achievements.append(
            {
                "idx": int(nom.get("idx", 0)),
                "slug": slug,
                "title": str(nom.get("title", slug)),
                "label": str(nom.get("label") or nom.get("title", slug)),
                "tier": str(nom.get("tier", tier_for_slug(slug, cfg))),
            }
        )
    achievements.sort(key=lambda a: a["idx"])
    return {
        "achievements": achievements,
        "stats": {
            "max_cp": int(record.get("max_checkpoint", -1)),
            "reward": float(record.get("episode_reward", 0)),
            "steps": int(record.get("episode_frames", 0)),
        },
        "show_until_frame": show_frames,
    }
