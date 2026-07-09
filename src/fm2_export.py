"""Экспорт inference_inputs.jsonl → FM2 (без reference/)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from inference_config import inference_fm2_guid
from log_utils import iter_jsonl
from project_paths import repo_root

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
_HEADER_KEYS_STRIP = frozenset({"guid", "length"})


def default_fm2_template(game_id: str = "rushn_attack") -> Path:
    """Шаблон заголовка FM2 вне games/…/reference/."""
    portable = repo_root() / "fceux" / "portable" / "movies"
    for name in (f"{game_id}-1.fm2", f"{game_id}.fm2"):
        candidate = portable / name
        if candidate.is_file():
            return candidate
    for fm2 in sorted(portable.glob("*.fm2")):
        return fm2
    raise FileNotFoundError(
        f"No FM2 template in {portable.as_posix()}. Pass --template explicitly."
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


def build_fm2_header(template: Path, *, guid: str | None = None) -> list[str]:
    """Заголовок FM2: ROM из шаблона + inference GUID. Без length — иначе FCEUX считает файл FM3/TAS Editor."""
    lines = read_fm2_header(template)
    lines.append(f"guid {guid or inference_fm2_guid()}")
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
    save_state: str | None = None,
    overlay: dict[str, Any] | None = None,
) -> Path:
    """Sidecar рядом с FM2: overlay + save_state для replay."""
    sidecar = fm2_path.with_suffix(".overlay.json")
    payload: dict[str, Any] = dict(overlay or {})
    if save_state:
        payload["save_state"] = save_state
    sidecar.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return sidecar


def write_fm2_artifacts(
    fm2_path: Path,
    *,
    save_state: str | None = None,
    overlay: dict[str, Any] | None = None,
) -> Path:
    """Sidecar .overlay.json для корректного replay."""
    return write_fm2_sidecar(fm2_path, save_state=save_state, overlay=overlay)


def export_fm2(
    jsonl_path: Path,
    out_path: Path,
    *,
    template: Path | None = None,
    episode: int | None = None,
    frame_skip: int = DEFAULT_FRAME_SKIP,
    save_state: str | None = None,
    overlay: dict[str, Any] | None = None,
) -> int:
    """jsonl → .fm2; возвращает число FM2-кадров."""
    tmpl = template or default_fm2_template()
    rows = list(iter_jsonl(jsonl_path))
    if not rows:
        raise ValueError(f"No rows in {jsonl_path}")

    frame_lines = list(iter_episode_frames(rows, episode=episode, frame_skip=frame_skip))
    header = build_fm2_header(tmpl)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        for line in header:
            f.write(line + "\n")
        for frame_line in frame_lines:
            f.write(frame_line + "\n")
    if save_state or overlay:
        write_fm2_sidecar(out_path, save_state=save_state, overlay=overlay)
    return len(frame_lines)


def export_episode_fm2_from_steps(
    steps: list[dict[str, Any]],
    out_path: Path,
    *,
    template: Path | None = None,
    frame_skip: int = DEFAULT_FRAME_SKIP,
    save_state: str | None = None,
    overlay: dict[str, Any] | None = None,
) -> int:
    """In-memory steps [{action}, …] → FM2."""
    tmpl = template or default_fm2_template()
    frame_lines: list[str] = []
    for row in steps:
        action = str(row.get("action", ""))
        for _ in range(frame_skip):
            frame_lines.append(fm2_frame_line(action))

    header = build_fm2_header(tmpl)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        for line in header:
            f.write(line + "\n")
        for frame_line in frame_lines:
            f.write(frame_line + "\n")
    if save_state or overlay:
        write_fm2_sidecar(out_path, save_state=save_state, overlay=overlay)
    return len(frame_lines)
