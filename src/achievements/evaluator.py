"""Оценка achievements по logs/<model_version>/attempts.jsonl."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonl_logs import load_jsonl
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


def _append_tag(record: dict[str, Any], slug: str) -> None:
    tags = record.setdefault("tags", [])
    if slug not in tags:
        tags.append(slug)


def evaluate_records(
    records: list[dict[str, Any]],
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Вернуть копии записей с заполненным tags[]."""
    achievements_config = config or load_achievements_config()
    out = [dict(r) for r in records]
    for record in out:
        record["tags"] = []

    noms = list(achievements_config.get("nominations") or [])

    # instant rules
    for record in out:
        for nom in noms:
            if nom.get("type") != "instant":
                continue
            if _matches_instant(record, nom.get("condition") or {}):
                _append_tag(record, nom["slug"])

    # death_cluster (wall / …)
    for nom in noms:
        if nom.get("type") != "death_cluster":
            continue
        slug = str(nom["slug"])
        min_count = int(nom.get("min_count", 3))
        counts: Counter[tuple[str, int]] = Counter()
        for record in out:
            key = _death_key(record)
            if key:
                counts[key] += 1
        for record in out:
            key = _death_key(record)
            if key and counts[key] >= min_count:
                _append_tag(record, slug)

    # new_max_checkpoint (new_frontier / …)
    for nom in noms:
        if nom.get("type") != "new_max_checkpoint":
            continue
        slug = str(nom["slug"])
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
                if best_by_model[mv] >= 0:
                    _append_tag(record, slug)
                best_by_model[mv] = cp

    # regression: откат от текущего best max_checkpoint модели в пуле
    for nom in noms:
        if nom.get("type") != "regression":
            continue
        slug = str(nom["slug"])
        min_drop = int(nom.get("min_drop", 2))
        best_by_model: dict[str, int] = defaultdict(lambda: -1)
        ordered = sorted(
            out,
            key=lambda r: _parse_ts(r.get("timestamp"))
            or datetime.min.replace(tzinfo=timezone.utc),
        )
        for record in ordered:
            mv = str(record.get("model_version", ""))
            cp = int(record.get("max_checkpoint", -1))
            best = best_by_model[mv]
            if best >= 0 and (best - cp) >= min_drop:
                _append_tag(record, slug)
            if cp > best_by_model[mv]:
                best_by_model[mv] = cp

    # top_k по полю
    for nom in noms:
        if nom.get("type") != "top_k":
            continue
        slug = str(nom["slug"])
        k = int(nom.get("k", 3))
        field = str(nom.get("field", "episode_reward"))
        ranked = sorted(out, key=lambda r: float(r.get(field, 0)), reverse=True)
        top_ids = {id(r) for r in ranked[:k]}
        for record in out:
            if id(record) in top_ids:
                _append_tag(record, slug)

    return out


def evaluate_attempts_file(
    attempts_path: Path,
    *,
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    achievements_config = config or load_achievements_config()
    records = load_jsonl(attempts_path)
    return evaluate_records(records, achievements_config)


def write_tagged_attempts(attempts_path: Path, records: list[dict[str, Any]]) -> None:
    """Перезаписать attempts.jsonl строками пула (с tags[])."""
    with attempts_path.open("w", encoding="utf-8") as f:
        for row in records:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def tier_for_slug(slug: str, config: dict[str, Any] | None = None) -> str:
    achievements_config = config or load_achievements_config()
    for nom in achievements_config.get("nominations") or []:
        if nom.get("slug") == slug:
            return str(nom.get("tier", "gold"))
    return "gold"


def overlay_payload(
    record: dict[str, Any],
    *,
    config: dict[str, Any] | None = None,
    show_frames: int = 180,
) -> dict[str, Any]:
    """JSON sidecar для Lua HUD (slim: gen, CP, тег, смерть)."""
    achievements_config = config or load_achievements_config()
    noms = _nomination_by_slug(achievements_config)
    achievements = []
    for slug in record.get("tags") or []:
        nom = noms.get(slug, {})
        achievements.append(
            {
                "idx": int(nom.get("idx", 0)),
                "slug": slug,
                "title": str(nom.get("title", slug)),
                "label": str(nom.get("label") or nom.get("title", slug)),
                "tier": str(nom.get("tier", tier_for_slug(slug, achievements_config))),
            }
        )
    achievements.sort(key=lambda a: a["idx"])
    primary = achievements[0] if achievements else None
    payload: dict[str, Any] = {
        "model_version": str(record.get("model_version") or ""),
        "achievements": achievements,
        "tag": (primary or {}).get("label") or (primary or {}).get("slug") or "",
        "stats": {
            "max_cp": int(record.get("max_checkpoint", -1)),
        },
        "show_until_frame": show_frames,
    }
    if record.get("died"):
        death: dict[str, Any] = {}
        if record.get("death_room") is not None:
            death["room"] = str(record.get("death_room"))
        if record.get("death_x") is not None:
            death["x"] = int(record["death_x"])
        if death:
            payload["death"] = death
    return payload
