"""Сборка FM2-плейлиста по номинациям achievements."""

from __future__ import annotations



import hashlib

import json

import re

import shutil

from pathlib import Path

from typing import Any



from achievements.evaluator import evaluate_attempts_file, load_achievements_config, overlay_payload

from fm2_export import export_fm2, episode_fm2_guid, fm2_has_embedded_savestate, remap_fm2_guid, write_fm2_sidecar

from inference_states import resolve_inference_reset_state

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





def _fm2_digest(path: Path) -> str:

    """MD5 покадровой части FM2 (строки |…) — одинаковый геймплей → один клип."""

    digest = hashlib.md5()

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():

        if line.startswith("|"):

            digest.update(line.encode("utf-8"))

    return digest.hexdigest()





def _strip_legacy_save_state(overlay_path: Path) -> None:

    if not overlay_path.is_file():

        return

    payload = json.loads(overlay_path.read_text(encoding="utf-8"))

    if "save_state" not in payload:

        return

    del payload["save_state"]

    overlay_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")





def _playlist_clip_name(date_prefix: str, name: str) -> bool:
    """Имена клипов плейлиста: YYYYMMDD_NN_slug_NNN.fm2 / .overlay.json (не ep0001)."""
    return bool(re.match(rf"^{re.escape(date_prefix)}_\d{{2}}_.+", name))


def cleanup_playlist_clips(logs_dir: Path, *, date_prefix: str | None = None) -> int:
    """Удалить FM2/overlay клипов плейлиста за день (перед пересборкой)."""
    prefix = date_prefix or utc_date_prefix()
    removed = 0
    if not logs_dir.is_dir():
        return 0
    for path in list(logs_dir.iterdir()):
        if not _playlist_clip_name(prefix, path.name):
            continue
        if path.name.endswith(".fm2") or path.name.endswith(".overlay.json"):
            path.unlink(missing_ok=True)
            removed += 1
    for name in (f"{prefix}_playlist.json", f"{prefix}_playlist.play.cmd"):
        p = logs_dir / name
        if p.is_file():
            p.unlink(missing_ok=True)
            removed += 1
    return removed


def _write_file_clone(src: Path, dest: Path) -> None:
    """Скопировать файл через .tmp (меньше WinError 32 при перезаписи)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_bytes(src.read_bytes())
    if dest.exists():
        dest.unlink()
    tmp.rename(dest)


def _copy_overlay_sidecar(

    src_fm2: Path,

    dest_fm2: Path,

    *,

    record: dict[str, Any],

    config: dict[str, Any],

) -> Path:

    """Собрать .overlay.json рядом с FM2 в плейлисте (атомарная запись — меньше WinError 32)."""
    dest_overlay = dest_fm2.with_suffix(".overlay.json")
    src_overlay = src_fm2.with_suffix(".overlay.json")
    if src_overlay.is_file():
        payload = json.loads(src_overlay.read_text(encoding="utf-8"))
        if "save_state" in payload:
            del payload["save_state"]
    else:
        payload = overlay_payload(record, config=config)
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

    dedupe: bool = True,

) -> tuple[dict[str, list[Path]], Path | None, int]:

    """Создать FM2-копии, overlay sidecar и YYYYMMDD_playlist.json.



    Возвращает ({slug: [fm2 paths]}, manifest_path | None, число клипов).

    """

    achievements_config = config or load_achievements_config()

    records = evaluate_attempts_file(attempts_path, config=achievements_config)

    date_prefix = utc_date_prefix()

    cleanup_playlist_clips(logs_dir, date_prefix=date_prefix)

    noms = _nomination_index(achievements_config)

    broadcast = achievements_config.get("broadcast_order") or list(noms.keys())

    mission_root = mission_dir(game, mission)

    reset_state_rel = resolve_inference_reset_state(mission_root)

    embed_save_state_path = mission_root / reset_state_rel



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

            dest = logs_dir / f"{date_prefix}_{nom_idx:02d}_{slug}_{clip_num + 1:03d}.fm2"

            src = record.get("fm2_path")

            if src and Path(src).is_file():

                _write_file_clone(Path(src), dest)

                remap_fm2_guid(dest, episode_fm2_guid(salt=dest.stem))

                if not fm2_has_embedded_savestate(dest):

                    raise ValueError(f"Source FM2 is not self-contained: {src}")

            elif inference_inputs_path and inference_inputs_path.is_file():

                export_fm2(

                    inference_inputs_path,

                    dest,

                    episode=int(record.get("episode", 0)),

                    save_state_path=embed_save_state_path,

                )

            else:

                continue

            overlay_path = _copy_overlay_sidecar(

                Path(src) if src else dest,

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

                    "fm2": dest.name,

                    "overlay": overlay_path.name,

                }

            )



        if paths:

            created[slug] = paths



    manifest_path: Path | None = None

    if manifest_clips:

        manifest_path = write_playlist_manifest(manifest_clips, logs_dir, date_prefix=date_prefix)

        write_playlist_launcher(manifest_path, game=game, mission=mission)



    return created, manifest_path, len(manifest_clips)


