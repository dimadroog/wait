"""Сборка FM2-плейлиста по номинациям achievements (фаза C3)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from achievements.airtime import measure_playlist_airtime
from achievements.evaluator import evaluate_attempts_file, load_achievements_config, overlay_payload
from fm2_export import (
    episode_fm2_guid,
    export_fm2,
    fm2_has_embedded_savestate,
    refresh_fm2_embedded_savestate,
    remap_fm2_guid,
    trim_fm2_tail_frames,
)
from inference_states import resolve_inference_reset_state
from jsonl_logs import dated_day_dir, utc_date_prefix
from project_paths import mission_dir, repo_root

PAD_SLUG = "pad"
PAD_IDX = 99
PAD_LABEL = "Pad"
# После death FM2 хвостом: game over → title/attract. death_x=129 = title-сигнатура Rush'n Attack.
DIED_ATTRACT_TAIL_FRAMES = 900
DIED_TITLE_X_TAIL_FRAMES = 1500  # death_x==129: сильнее (game over + title)
DIED_ATTRACT_MIN_KEEP_FRAMES = 60
# Классический title/attract x (ISSUE_INFERENCE / G0).
TITLE_ATTRACT_X = 129


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


def _fm2_digest(path: Path) -> str:
    """MD5 покадровой части FM2 (строки |…) — одинаковый геймплей → один клип."""
    digest = hashlib.md5()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("|"):
            digest.update(line.encode("utf-8"))
    return digest.hexdigest()


def _playlist_clip_name(name: str) -> bool:
    """Имена клипов плейлиста: NN_slug_NNN.fm2 / .overlay.json (не ep0001)."""
    return bool(re.match(r"^\d{2}_.+", name))


def cleanup_playlist_clips(logs_dir: Path, *, date_prefix: str | None = None) -> int:
    """Удалить FM2/overlay клипов плейлиста за день (перед пересборкой)."""
    prefix = date_prefix or utc_date_prefix()
    day_dir = logs_dir / prefix
    removed = 0
    if not day_dir.is_dir():
        return 0
    for path in list(day_dir.iterdir()):
        if not _playlist_clip_name(path.name):
            continue
        if path.name.endswith(".fm2") or path.name.endswith(".overlay.json"):
            path.unlink(missing_ok=True)
            removed += 1
    for name in ("playlist.json", "playlist.play.cmd"):
        p = day_dir / name
        if p.is_file():
            p.unlink(missing_ok=True)
            removed += 1
    return removed


def cleanup_episode_raw_fm2(logs_dir: Path, *, date_prefix: str | None = None) -> int:
    """Удалить промежуточные epNNNN.fm2 / .overlay.json (канон — номинации плейлиста)."""
    prefix = date_prefix or utc_date_prefix()
    day_dir = logs_dir / prefix
    removed = 0
    if not day_dir.is_dir():
        return 0
    for path in list(day_dir.iterdir()):
        name = path.name
        if not name.startswith("ep"):
            continue
        if name.endswith(".fm2") or name.endswith(".overlay.json"):
            path.unlink(missing_ok=True)
            removed += 1
    return removed


def _write_file_clone(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_bytes(src.read_bytes())
    if dest.exists():
        dest.unlink()
    tmp.rename(dest)


def write_overlay_clip(
    dest: Path,
    *,
    record: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> Path:
    """Записать .overlay.json без save_state (sidecar к FM2)."""
    payload = overlay_payload(record, config=config or load_achievements_config())
    payload.pop("save_state", None)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if dest.exists():
        dest.unlink()
    tmp.rename(dest)
    return dest


def _copy_overlay_sidecar(
    src_fm2: Path,
    dest_fm2: Path,
    *,
    record: dict[str, Any],
    config: dict[str, Any],
) -> Path:
    dest_overlay = dest_fm2.with_suffix(".overlay.json")
    src_overlay = src_fm2.with_suffix(".overlay.json")
    if src_overlay.is_file():
        payload = json.loads(src_overlay.read_text(encoding="utf-8"))
        payload.pop("save_state", None)
        dest_overlay.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest_overlay.with_suffix(".overlay.json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        if dest_overlay.exists():
            dest_overlay.unlink()
        tmp.rename(dest_overlay)
        return dest_overlay
    return write_overlay_clip(dest_overlay, record=record, config=config)


def write_playlist_manifest(
    clips: list[dict[str, Any]],
    day_dir: Path,
    *,
    date_prefix: str,
    include_airtime: bool = True,
) -> Path:
    manifest: dict[str, Any] = {"date": date_prefix, "clips": clips}
    path = day_dir / "playlist.json"
    if include_airtime and clips:
        airtime = measure_playlist_airtime(manifest, logs_dir=day_dir)
        manifest["airtime"] = airtime.as_dict()
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
        f".venv\\Scripts\\python.exe scripts\\play_inference_fm2.py {rel_manifest} "
        f"--game {game} --mission {mission} --skip-preflight",
        "if errorlevel 1 pause",
    ]
    launcher.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    return launcher


def _resolve_source_fm2(record: dict[str, Any], day_dir: Path) -> Path | None:
    src = record.get("fm2_path")
    if src and Path(src).is_file():
        return Path(src)
    episode = int(record.get("episode", -1))
    if episode < 0:
        return None
    conventional = day_dir / f"ep{episode:04d}.fm2"
    if conventional.is_file():
        return conventional
    return None


def _died_tail_trim_frames(record: dict[str, Any]) -> int:
    if not record.get("died"):
        return 0
    try:
        death_x = int(record.get("death_x")) if record.get("death_x") is not None else None
    except (TypeError, ValueError):
        death_x = None
    if death_x == TITLE_ATTRACT_X:
        return DIED_TITLE_X_TAIL_FRAMES
    return DIED_ATTRACT_TAIL_FRAMES


def _trim_died_attract_tail(dest: Path, record: dict[str, Any]) -> int:
    """Срезать game over / title/attract-хвост у клипов с died=True."""
    drop = _died_tail_trim_frames(record)
    if drop <= 0:
        return 0
    return trim_fm2_tail_frames(
        dest,
        drop,
        min_keep=DIED_ATTRACT_MIN_KEEP_FRAMES,
    )


def _materialize_clip_fm2(
    *,
    record: dict[str, Any],
    dest: Path,
    day_dir: Path,
    embed_save_state_path: Path,
    inference_inputs_path: Path | None,
    game: str,
    mission: str,
) -> Path | None:
    """Записать self-contained FM2. Возвращает путь для overlay-sidecar (src|dest) или None."""
    src = _resolve_source_fm2(record, day_dir)
    clip_guid = episode_fm2_guid(salt=dest.stem)
    if src is not None:
        _write_file_clone(src, dest)
        remap_fm2_guid(dest, clip_guid)
        refresh_fm2_embedded_savestate(dest, embed_save_state_path, guid=clip_guid)
        if not fm2_has_embedded_savestate(dest):
            raise ValueError(f"Source FM2 is not self-contained: {src}")
        _trim_died_attract_tail(dest, record)
        return src
    if inference_inputs_path and inference_inputs_path.is_file():
        export_fm2(
            inference_inputs_path,
            dest,
            episode=int(record.get("episode", 0)),
            save_state_path=embed_save_state_path,
            game_id=game,
            mission_id=mission,
        )
        remap_fm2_guid(dest, clip_guid)
        refresh_fm2_embedded_savestate(dest, embed_save_state_path, guid=clip_guid)
        _trim_died_attract_tail(dest, record)
        return dest
    return None


def _manifest_airtime_seconds(manifest_clips: list[dict[str, Any]], day_dir: Path) -> float:
    if not manifest_clips:
        return 0.0
    return measure_playlist_airtime({"clips": manifest_clips}, logs_dir=day_dir).seconds


def _append_pad_clips(
    *,
    records: list[dict[str, Any]],
    manifest_clips: list[dict[str, Any]],
    created: dict[str, list[Path]],
    day_dir: Path,
    achievements_config: dict[str, Any],
    embed_save_state_path: Path,
    inference_inputs_path: Path | None,
    game: str,
    mission: str,
    pad_to_seconds: float,
) -> int:
    """Добить плейлист клипами вне номинаций (после broadcast_order), пока airtime ≥ target."""
    used_episodes = {int(c.get("episode", -1)) for c in manifest_clips}
    pad_num = 0
    clip_seq = len(manifest_clips)
    paths = list(created.get(PAD_SLUG) or [])

    candidates = sorted(
        records,
        key=lambda r: int(r.get("episode_frames", 0) or 0),
        reverse=True,
    )
    for record in candidates:
        if _manifest_airtime_seconds(manifest_clips, day_dir) >= pad_to_seconds:
            break
        episode = int(record.get("episode", -1))
        if episode < 0 or episode in used_episodes:
            continue

        dest = day_dir / f"{PAD_IDX:02d}_{PAD_SLUG}_{pad_num + 1:03d}.fm2"
        overlay_src = _materialize_clip_fm2(
            record=record,
            dest=dest,
            day_dir=day_dir,
            embed_save_state_path=embed_save_state_path,
            inference_inputs_path=inference_inputs_path,
            game=game,
            mission=mission,
        )
        if overlay_src is None:
            continue

        overlay_path = _copy_overlay_sidecar(
            overlay_src,
            dest,
            record=record,
            config=achievements_config,
        )
        pad_num += 1
        clip_seq += 1
        used_episodes.add(episode)
        paths.append(dest)
        manifest_clips.append(
            {
                "idx": clip_seq,
                "slug": PAD_SLUG,
                "block_label": PAD_LABEL,
                "episode": episode,
                "fm2": dest.name,
                "overlay": overlay_path.name,
            }
        )

    if paths:
        created[PAD_SLUG] = paths
    return pad_num


def build_playlist(
    attempts_path: Path,
    logs_dir: Path,
    *,
    config: dict[str, Any] | None = None,
    inference_inputs_path: Path | None = None,
    game: str = "rushn_attack",
    mission: str = "m1",
    dedupe: bool = True,
    pad_to_seconds: float | None = None,
) -> tuple[dict[str, list[Path]], Path | None, int]:
    """Создать FM2-копии, overlay sidecar и logs/YYYYMMDD/playlist.json.

    pad_to_seconds: после блоков номинаций добить клипами (slug=pad), пока airtime ≥ N.
    """
    achievements_config = config or load_achievements_config()
    records = evaluate_attempts_file(attempts_path, config=achievements_config)
    date_prefix = utc_date_prefix()
    day_dir = dated_day_dir(logs_dir)
    cleanup_playlist_clips(logs_dir, date_prefix=date_prefix)

    noms = _nomination_index(achievements_config)
    broadcast = achievements_config.get("broadcast_order") or list(noms.keys())
    mission_root = mission_dir(game, mission)
    embed_save_state_path = mission_root / resolve_inference_reset_state(mission_root)

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
            dest = day_dir / f"{nom_idx:02d}_{slug}_{clip_num + 1:03d}.fm2"
            overlay_src = _materialize_clip_fm2(
                record=record,
                dest=dest,
                day_dir=day_dir,
                embed_save_state_path=embed_save_state_path,
                inference_inputs_path=inference_inputs_path,
                game=game,
                mission=mission,
            )
            if overlay_src is None:
                continue

            overlay_path = _copy_overlay_sidecar(
                overlay_src,
                dest,
                record=record,
                config=achievements_config,
            )

            if dedupe:
                digest = _fm2_digest(dest)
                if digest in seen_digests:
                    dest.unlink(missing_ok=True)
                    overlay_path.unlink(missing_ok=True)
                    continue
                seen_digests.add(digest)

            clip_num += 1
            paths.append(dest)
            clip_seq += 1
            manifest_clips.append(
                {
                    "idx": clip_seq,
                    "slug": slug,
                    "block_label": label,
                    "episode": int(record.get("episode", 0)),
                    "fm2": dest.name,
                    "overlay": overlay_path.name,
                }
            )

        if paths:
            created[slug] = paths

    if pad_to_seconds is not None and pad_to_seconds > 0:
        _append_pad_clips(
            records=records,
            manifest_clips=manifest_clips,
            created=created,
            day_dir=day_dir,
            achievements_config=achievements_config,
            embed_save_state_path=embed_save_state_path,
            inference_inputs_path=inference_inputs_path,
            game=game,
            mission=mission,
            pad_to_seconds=pad_to_seconds,
        )

    manifest_path: Path | None = None
    if manifest_clips:
        manifest_path = write_playlist_manifest(manifest_clips, day_dir, date_prefix=date_prefix)
        write_playlist_launcher(manifest_path, game=game, mission=mission)

    # Канон в logs/YYYYMMDD/: NN_slug_MMM.fm2 — сырые epNNNN убрать после сборки.
    cleanup_episode_raw_fm2(logs_dir, date_prefix=date_prefix)

    return created, manifest_path, len(manifest_clips)
