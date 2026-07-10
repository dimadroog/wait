"""Сборка FM2-плейлиста по номинациям achievements."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from achievements.evaluator import evaluate_attempts_file, load_achievements_config, overlay_payload
from fm2_export import export_fm2, fm2_has_embedded_savestate, write_fm2_sidecar
from inference_config import resolve_inference_save_state
from log_utils import utc_date_prefix
from project_paths import repo_root


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


def _strip_save_state_from_overlay(overlay_path: Path) -> None:
    if not overlay_path.is_file():
        return
    payload = json.loads(overlay_path.read_text(encoding="utf-8"))
    if "save_state" not in payload:
        return
    del payload["save_state"]
    overlay_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _copy_overlay_sidecar(
    src_fm2: Path,
    dest_fm2: Path,
    *,
    record: dict[str, Any],
    config: dict[str, Any],
    default_save_state: str,
) -> Path:
    """Скопировать или собрать .overlay.json рядом с FM2 в плейлисте."""
    dest_overlay = dest_fm2.with_suffix(".overlay.json")
    embedded = fm2_has_embedded_savestate(dest_fm2)
    src_overlay = src_fm2.with_suffix(".overlay.json")
    if src_overlay.is_file():
        shutil.copy2(src_overlay, dest_overlay)
        if embedded:
            _strip_save_state_from_overlay(dest_overlay)
        return dest_overlay
    save_state = None if embedded else str(record.get("save_state") or default_save_state)
    payload = overlay_payload(record, config=config)
    return write_fm2_sidecar(dest_fm2, save_state=save_state, overlay=payload)


def _manifest_save_state(dest_fm2: Path, overlay_path: Path, default_save_state: str) -> str | None:
    if fm2_has_embedded_savestate(dest_fm2):
        return None
    overlay_meta = json.loads(overlay_path.read_text(encoding="utf-8"))
    return str(overlay_meta.get("save_state") or default_save_state)


def write_playlist_manifest(
    clips: list[dict[str, Any]],
    logs_dir: Path,
    *,
    date_prefix: str,
) -> Path:
    """Записать logs/YYYYMMDD_playlist.json."""
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
    """Windows launcher: один эфирный запуск play_inference_fm2.py с manifest."""
    launcher = manifest_path.with_suffix(".play.cmd")
    rel_manifest = manifest_path.resolve().relative_to(repo_root()).as_posix()
    lines = [
        "@echo off",
        f'cd /d "{repo_root()}"',
        f".venv\\Scripts\\python.exe scripts\\play_inference_fm2.py {rel_manifest} --game {game} --mission {mission}",
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
) -> tuple[dict[str, list[Path]], Path | None, int]:
    """Создать FM2-копии, overlay sidecar и YYYYMMDD_playlist.json.

    Возвращает ({slug: [fm2 paths]}, manifest_path | None, число клипов).
    """
    cfg = config or load_achievements_config()
    records = evaluate_attempts_file(attempts_path, config=cfg)
    date_prefix = utc_date_prefix()
    noms = _nomination_index(cfg)
    broadcast = cfg.get("broadcast_order") or list(noms.keys())
    default_save_state = resolve_inference_save_state(
        logs_dir.parent,
        cp_index=0,
    )
    embed_save_state_path = logs_dir.parent / default_save_state

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
    logs_dir.mkdir(parents=True, exist_ok=True)

    for slug in broadcast:
        items = by_slug.get(slug) or []
        if not items:
            continue
        nom = noms[slug]
        nom_idx = int(nom.get("idx", 0))
        label = _block_label(nom)
        paths: list[Path] = []
        for seq, record in enumerate(items, start=1):
            dest = logs_dir / f"{date_prefix}_{nom_idx:02d}_{slug}_{seq:03d}.fm2"
            src = record.get("fm2_path")
            if src and Path(src).is_file():
                shutil.copy2(src, dest)
            elif inference_inputs_path and inference_inputs_path.is_file():
                export_fm2(
                    inference_inputs_path,
                    dest,
                    episode=int(record.get("episode", 0)),
                    embed_savestate=embed_save_state_path.is_file(),
                    save_state_path=embed_save_state_path if embed_save_state_path.is_file() else None,
                )
            else:
                continue
            overlay_path = _copy_overlay_sidecar(
                Path(src) if src else dest,
                dest,
                record=record,
                config=cfg,
                default_save_state=default_save_state,
            )
            save_state = _manifest_save_state(dest, overlay_path, default_save_state)
            paths.append(dest)
            clip_seq += 1
            manifest_clips.append(
                {
                    "idx": clip_seq,
                    "slug": slug,
                    "block_label": label,
                    "fm2": dest.name,
                    "overlay": overlay_path.name,
                    "save_state": save_state,
                }
            )

        if paths:
            created[slug] = paths

    manifest_path: Path | None = None
    if manifest_clips:
        manifest_path = write_playlist_manifest(manifest_clips, logs_dir, date_prefix=date_prefix)
        write_playlist_launcher(manifest_path, game=game, mission=mission)

    return created, manifest_path, len(manifest_clips)
