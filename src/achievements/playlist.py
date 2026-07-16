"""Сборка плейлиста попыток inference по номинациям achievements (BACKLOG 3.4)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from achievements.evaluator import evaluate_attempts_file, load_achievements_config, overlay_payload
from inference_replay import episode_action_digest
from jsonl_logs import utc_date_prefix
from project_paths import mission_dir, repo_root


def _sort_key_for_slug(slug: str, record: dict[str, Any]) -> tuple:
    if slug == "episode_reward":
        return (-float(record.get("episode_reward", 0)),)
    if slug == "fastest_death":
        return (int(record.get("episode_frames", 999)),)
    ts = str(record.get("timestamp", ""))
    return (ts,)


def _nomination_index(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {n["slug"]: n for n in config.get("nominations") or []}


def _block_label(nom: dict[str, Any]) -> str:
    return str(nom.get("label") or nom.get("title", ""))


def _playlist_clip_name(date_prefix: str, name: str) -> bool:
    """Клипы плейлиста: YYYYMMDD_NN_slug_NNN.overlay.json"""
    return bool(re.match(rf"^{re.escape(date_prefix)}_\d{{2}}_.+\.overlay\.json$", name))


def cleanup_playlist_clips(logs_dir: Path, *, date_prefix: str | None = None) -> int:
    """Удалить overlay/manifest плейлиста за день (перед пересборкой)."""
    prefix = date_prefix or utc_date_prefix()
    removed = 0
    if not logs_dir.is_dir():
        return 0
    for path in list(logs_dir.iterdir()):
        if _playlist_clip_name(prefix, path.name):
            path.unlink(missing_ok=True)
            removed += 1
    for name in (f"{prefix}_playlist.json", f"{prefix}_playlist.play.cmd"):
        p = logs_dir / name
        if p.is_file():
            p.unlink(missing_ok=True)
            removed += 1
    return removed


def write_overlay_clip(
    dest_overlay: Path,
    *,
    record: dict[str, Any],
    config: dict[str, Any],
) -> Path:
    dest_overlay.parent.mkdir(parents=True, exist_ok=True)
    payload = overlay_payload(record, config=config)
    payload.pop("save_state", None)
    tmp = dest_overlay.with_suffix(".overlay.json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if dest_overlay.exists():
        dest_overlay.unlink()
    tmp.rename(dest_overlay)
    return dest_overlay


def write_playlist_manifest(
    clips: list[dict[str, Any]],
    logs_dir: Path,
    *,
    date_prefix: str,
) -> Path:
    manifest = {"date": date_prefix, "clips": clips}
    path = logs_dir / f"{date_prefix}_playlist.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_playlist_launcher(
    manifest_path: Path,
    *,
    game: str = "rushn_attack",
    mission: str = "m1",
) -> Path:
    launcher = manifest_path.with_suffix(".play.cmd")
    rel_manifest = manifest_path.resolve().relative_to(repo_root()).as_posix()
    lines = [
        "@echo off",
        f'cd /d "{repo_root()}"',
        f".venv\\Scripts\\python.exe scripts\\play_inference_fm2.py {rel_manifest} --game {game} --mission {mission} --skip-preflight",
        "if errorlevel 1 pause",
    ]
    launcher.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    return launcher


def build_playlist(
    attempts_path: Path,
    logs_dir: Path,
    *,
    config: dict[str, Any] | None = None,
    inference_inputs_path: Path | None = None,
    game: str = "rushn_attack",
    mission: str = "m1",
    dedupe: bool = True,
) -> tuple[dict[str, list[Path]], Path | None, int]:
    """Собрать playlist.json: клипы = episode + inference_inputs + overlay."""
    if inference_inputs_path is None or not inference_inputs_path.is_file():
        raise ValueError(f"inference_inputs.jsonl required: {inference_inputs_path}")

    achievements_config = config or load_achievements_config()
    records = evaluate_attempts_file(attempts_path, config=achievements_config)
    date_prefix = utc_date_prefix()
    cleanup_playlist_clips(logs_dir, date_prefix=date_prefix)

    noms = _nomination_index(achievements_config)
    broadcast = achievements_config.get("broadcast_order") or list(noms.keys())
    inputs_name = inference_inputs_path.name

    by_slug: dict[str, list[dict[str, Any]]] = {slug: [] for slug in noms}
    for record in records:
        for slug in record.get("tags") or []:
            if slug in by_slug:
                by_slug[slug].append(record)

    for slug, items in by_slug.items():
        items.sort(key=lambda r: _sort_key_for_slug(slug, r))

    created: dict[str, list[Path]] = {}
    manifest_clips: list[dict[str, Any]] = []
    clip_seq = 0
    seen_digests: set[str] = set()
    logs_dir.mkdir(parents=True, exist_ok=True)

    for slug in broadcast:
        items = by_slug.get(slug) or []
        if not items:
            continue
        nom = noms[slug]
        nom_idx = int(nom.get("idx", 0))
        label = _block_label(nom)
        paths: list[Path] = []
        clip_num = 0

        for record in items:
            episode = int(record.get("episode", -1))
            if episode < 0:
                continue
            try:
                episode_action_digest(inference_inputs_path, episode)
            except ValueError:
                continue

            if dedupe:
                digest = episode_action_digest(inference_inputs_path, episode)
                if digest in seen_digests:
                    continue
                seen_digests.add(digest)

            clip_num += 1
            dest_overlay = logs_dir / f"{date_prefix}_{nom_idx:02d}_{slug}_{clip_num:03d}.overlay.json"
            write_overlay_clip(dest_overlay, record=record, config=achievements_config)
            paths.append(dest_overlay)
            clip_seq += 1
            manifest_clips.append(
                {
                    "idx": clip_seq,
                    "slug": slug,
                    "block_label": label,
                    "episode": episode,
                    "inference_inputs": inputs_name,
                    "overlay": dest_overlay.name,
                }
            )

        if paths:
            created[slug] = paths

    manifest_path: Path | None = None
    if manifest_clips:
        manifest_path = write_playlist_manifest(manifest_clips, logs_dir, date_prefix=date_prefix)
        write_playlist_launcher(manifest_path, game=game, mission=mission)

    return created, manifest_path, len(manifest_clips)
