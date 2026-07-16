"""Экспорт inference_inputs.jsonl → FM2."""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any, Iterator

from jsonl_logs import iter_jsonl
from project_paths import game_dir, load_yaml, mission_dir

# Отдельный GUID от эталона (clear.fm2) и от reference/header.fm2 (шаблон ...0001).
INFERENCE_FM2_GUID = "B1AEF103-0001-4000-8000-000000000002"
INFERENCE_FM2_GUID_NS = uuid.UUID(INFERENCE_FM2_GUID)


def episode_fm2_guid(episode: int | None = None, *, salt: str = "") -> str:
    """Уникальный GUID на эпизод — FCEUX иначе путает клипы с общим guid в одной папке."""
    if episode is None and not salt:
        return INFERENCE_FM2_GUID
    name = f"episode-{episode}" if episode is not None else "clip"
    if salt:
        name = f"{name}-{salt}"
    return str(uuid.uuid5(INFERENCE_FM2_GUID_NS, name)).upper()

# FCEUX FM2: RLDUTSBA
FM2_BUTTON_CHARS = "RLDUTSBA"
BRIDGE_TO_FM2 = {
    "right": 0,
    "left": 1,
    "down": 2,
    "up": 3,
    "start": 4,
    "select": 5,
    "B": 6,
    "A": 7,
}
EMPTY_PORT = "........"
DEFAULT_FRAME_SKIP = 4
_HEADER_KEYS_STRIP = frozenset({"guid", "length", "savestate"})
_GUID_BYTES_RE = re.compile(
    rb"[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}"
)
# FCEUX 2.6.6 FCS: movie GUID в фиксированном смещении (cp0 / inference_cp1+ @ 5699).
FCS_MOVIE_GUID_OFFSET = 5699
FCS_MOVIE_GUID_LEN = 36


def default_fm2_template(
    game_id: str = "rushn_attack",
    mission_id: str | None = None,
) -> Path:
    """Шаблон заголовка FM2 из games/…/reference/ (не fceux/portable/movies/)."""
    game_yaml = load_yaml(game_dir(game_id) / "game.yaml")
    mid = mission_id or str(game_yaml.get("default_mission", "m1"))
    reference = mission_dir(game_id, mid) / "reference"

    header = reference / "header.fm2"
    if header.is_file():
        return header

    manifest_path = mission_dir(game_id, mid) / "config" / "playthrough_manifest.yaml"
    if manifest_path.is_file():
        fm2_rel = load_yaml(manifest_path).get("fm2_file")
        if fm2_rel:
            etalon = mission_dir(game_id, mid) / str(fm2_rel)
            if etalon.is_file():
                return etalon

    for fm2 in sorted(reference.glob("*.fm2")):
        return fm2

    raise FileNotFoundError(
        f"No FM2 header template in {reference.as_posix()}. "
        "Add reference/header.fm2 or pass --template explicitly."
    )


def read_fm2_header(template: Path) -> list[str]:
    lines: list[str] = []
    with template.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("|"):
                break
            key = line.split(None, 1)[0] if line.strip() else ""
            if key in _HEADER_KEYS_STRIP:
                continue
            lines.append(line.rstrip("\r\n"))
    if not lines:
        raise ValueError(f"FM2 template has no header: {template}")
    return lines


def read_fm2_guid(fm2_path: Path) -> str | None:
    for line in fm2_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("guid "):
            parts = line.split(None, 1)
            return parts[1] if len(parts) > 1 else None
    return None


def fm2_has_embedded_savestate(fm2_path: Path) -> bool:
    return read_embedded_savestate_blob(fm2_path) is not None


def read_embedded_savestate_blob(fm2_path: Path) -> bytes | None:
    """Бинарный FCS из строки `savestate 0x…` в заголовке FM2."""
    for line in fm2_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("|"):
            break
        if line.startswith("savestate 0x"):
            hex_body = line.split(None, 1)[1]
            return bytes.fromhex(hex_body[2:])
    return None


PLAYBACK_SAVESTATE_NAME = "playback.fc0"


def stage_playback_savestate(
    fm2_path: Path,
    staging: Path,
    *,
    fallback_fc0: Path | None = None,
    state_name: str = PLAYBACK_SAVESTATE_NAME,
) -> Path:
    """Записать .fc0 в staging для `-loadstate` перед `-playmovie` (FCEUX win64)."""
    staging.mkdir(parents=True, exist_ok=True)
    dest = staging / state_name
    blob = read_embedded_savestate_blob(fm2_path)
    if blob is None:
        if fallback_fc0 is None or not fallback_fc0.is_file():
            raise FileNotFoundError(
                f"FM2 has no embedded savestate and no fallback .fc0: {fm2_path}"
            )
        blob = fallback_fc0.read_bytes()
        guid = read_fm2_guid(fm2_path)
        if guid:
            blob = ensure_savestate_movie_guid(blob, guid)
    dest.write_bytes(blob)
    return dest


def refresh_fm2_embedded_savestate(
    fm2_path: Path,
    save_state_path: Path,
    *,
    guid: str | None = None,
) -> bool:
    """Подменить embedded FCS из .fc0 и прописать GUID заголовка в blob."""
    eff_guid = guid or read_fm2_guid(fm2_path)
    if not eff_guid:
        raise ValueError(f"FM2 has no guid line: {fm2_path}")
    if not save_state_path.is_file():
        raise FileNotFoundError(f"Save state not found: {save_state_path}")
    hex_val = fc0_to_savestate_hex(save_state_path, target_guid=eff_guid)
    save_line = f"savestate {hex_val}"
    lines = fm2_path.read_text(encoding="utf-8", errors="replace").splitlines()
    out: list[str] = []
    replaced = False
    for line in lines:
        if line.startswith("savestate "):
            out.append(save_line)
            replaced = True
        else:
            out.append(line)
    if not replaced:
        insert_at = next((i for i, line in enumerate(out) if line.startswith("|")), len(out))
        out.insert(insert_at, save_line)
    fm2_path.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
    return True


def remap_fm2_guid(fm2_path: Path, new_guid: str) -> str:
    """Переписать guid в заголовке и в embedded savestate (in-place). Возвращает старый guid."""
    lines = fm2_path.read_text(encoding="utf-8", errors="replace").splitlines()
    old_guid = ""
    out: list[str] = []
    for line in lines:
        if line.startswith("guid "):
            parts = line.split(None, 1)
            old_guid = parts[1] if len(parts) > 1 else ""
            out.append(f"guid {new_guid}")
        elif line.startswith("savestate 0x"):
            hex_body = line.split(None, 1)[1]
            blob = bytes.fromhex(hex_body[2:])
            blob = ensure_savestate_movie_guid(blob, new_guid)
            out.append("savestate 0x" + blob.hex().upper())
        else:
            out.append(line)
    fm2_path.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
    return old_guid


def ensure_savestate_movie_guid(fcs: bytes, target_guid: str) -> bytes:
    """Прописать movie GUID в FCS: заменить существующий или записать в offset 5699."""
    target = target_guid.upper().encode("ascii")
    if len(target) != FCS_MOVIE_GUID_LEN:
        raise ValueError(f"invalid GUID length: {target_guid!r}")
    if target in fcs:
        return fcs
    matches = list(_GUID_BYTES_RE.finditer(fcs))
    if len(matches) == 1:
        start, end = matches[0].span()
        if fcs[start:end] == target:
            return fcs
        return fcs[:start] + target + fcs[end:]
    if len(matches) == 0 and len(fcs) >= FCS_MOVIE_GUID_OFFSET + FCS_MOVIE_GUID_LEN:
        start = FCS_MOVIE_GUID_OFFSET
        end = start + FCS_MOVIE_GUID_LEN
        if fcs[start:end] == target:
            return fcs
        return fcs[:start] + target + fcs[end:]
    if len(matches) > 1:
        raise ValueError(f"expected 0 or 1 movie GUID in save state, found {len(matches)}")
    return fcs


def patch_savestate_movie_guid(fcs: bytes, target_guid: str) -> bytes:
    """Заменить movie GUID в FCS/FCEUX save state на target_guid (если есть ровно один)."""
    return ensure_savestate_movie_guid(fcs, target_guid)


def fc0_to_savestate_hex(
    save_state_path: Path,
    *,
    target_guid: str | None = None,
) -> str:
    """FCEUX .fc0/.fcs → строка `0xHEX` для заголовка FM2."""
    blob = save_state_path.read_bytes()
    if target_guid:
        blob = ensure_savestate_movie_guid(blob, target_guid)
    return "0x" + blob.hex().upper()


def build_fm2_header(
    template: Path,
    *,
    guid: str | None = None,
    save_state_path: Path | None = None,
    embed_savestate: bool = False,
) -> list[str]:
    """Заголовок FM2: ROM из шаблона + inference GUID. Без length — иначе FCEUX считает файл FM3/TAS Editor."""
    lines = read_fm2_header(template)
    eff_guid = guid or INFERENCE_FM2_GUID
    lines.append(f"guid {eff_guid}")
    if embed_savestate:
        if save_state_path is None:
            raise ValueError("save_state_path is required when embed_savestate=True")
        hex_val = fc0_to_savestate_hex(save_state_path, target_guid=eff_guid)
        lines.append(f"savestate {hex_val}")
    return lines


def action_to_fm2_port(action: str) -> str:
    port = list(EMPTY_PORT)
    if action:
        for part in action.split("+"):
            part = part.strip()
            idx = BRIDGE_TO_FM2.get(part)
            if idx is not None:
                port[idx] = FM2_BUTTON_CHARS[idx]
    return "".join(port)


def fm2_frame_line(action: str, *, rerecord: int = 0) -> str:
    p1 = action_to_fm2_port(action)
    return f"|{rerecord}|{p1}|{EMPTY_PORT}||"


def build_empty_fm2(
    out_path: Path,
    *,
    template: Path,
    save_state_path: Path,
    guid: str,
    num_frames: int = 60,
) -> int:
    """FM2 с embed и пустыми кадрами (probe / тесты N4)."""
    if num_frames < 1:
        raise ValueError("num_frames must be >= 1")
    header = build_fm2_header(
        template,
        guid=guid,
        embed_savestate=True,
        save_state_path=save_state_path,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        for line in header:
            f.write(line + "\n")
        for _ in range(num_frames):
            f.write(fm2_frame_line("") + "\n")
    return num_frames


def iter_episode_frames(
    rows: list[dict[str, Any]],
    *,
    episode: int | None = None,
    frame_skip: int = DEFAULT_FRAME_SKIP,
) -> Iterator[str]:
    filtered = rows if episode is None else [r for r in rows if int(r.get("episode", -1)) == episode]
    for row in filtered:
        action = str(row.get("action", ""))
        for _ in range(frame_skip):
            yield fm2_frame_line(action)


def write_fm2_sidecar(
    fm2_path: Path,
    *,
    overlay: dict[str, Any] | None = None,
) -> Path:
    """Sidecar .overlay.json рядом с FM2 (N6 / тесты формата)."""
    sidecar = fm2_path.with_suffix(".overlay.json")
    payload: dict[str, Any] = dict(overlay or {})
    sidecar.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return sidecar


def export_episode_fm2_from_steps(
    steps: list[dict[str, Any]],
    out_path: Path,
    *,
    template: Path | None = None,
    frame_skip: int = DEFAULT_FRAME_SKIP,
    overlay: dict[str, Any] | None = None,
    game_id: str = "rushn_attack",
    mission_id: str = "m1",
    save_state_path: Path,
    episode: int | None = None,
) -> int:
    """In-memory steps [{action}, …] → self-contained FM2."""
    tmpl = template or default_fm2_template(game_id, mission_id)
    frame_lines: list[str] = []
    for row in steps:
        action = str(row.get("action", ""))
        for _ in range(frame_skip):
            frame_lines.append(fm2_frame_line(action))

    header = build_fm2_header(
        tmpl,
        guid=episode_fm2_guid(episode),
        embed_savestate=True,
        save_state_path=save_state_path,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        for line in header:
            f.write(line + "\n")
        for frame_line in frame_lines:
            f.write(frame_line + "\n")
    if overlay:
        write_fm2_sidecar(out_path, overlay=overlay)
    return len(frame_lines)
