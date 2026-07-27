"""Atomic checkpoint save/resume для PPO train."""
from __future__ import annotations

import json
import signal
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback


def checkpoint_zip_path(path: Path) -> Path:
    p = Path(path)
    if p.suffix.lower() != ".zip":
        p = p.with_suffix(".zip")
    return p


def sidecar_path(checkpoint: Path) -> Path:
    z = checkpoint_zip_path(checkpoint)
    return z.with_suffix(".train.json")


def read_sidecar(checkpoint: Path) -> dict[str, Any] | None:
    path = sidecar_path(checkpoint)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_sidecar(
    checkpoint: Path,
    *,
    target_timesteps: int,
    game: str,
    mission: str,
    n_envs: int,
    save_state: str,
    num_timesteps: int | None = None,
) -> Path:
    path = sidecar_path(checkpoint)
    payload: dict[str, Any] = {
        "target_timesteps": target_timesteps,
        "game": game,
        "mission": mission,
        "n_envs": n_envs,
        "save_state": save_state,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if num_timesteps is not None:
        payload["num_timesteps"] = num_timesteps
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def note_n_envs_change(sidecar: dict[str, Any] | None, n_envs: int) -> str | None:
    """Сообщение при смене --n-envs на continue; None если менять нечего.

    ``n_envs`` — hardware-ключ (число параллельных сред), не инвариант поколения.
    Sidecar поле ``n_envs`` = последний прогон; hard-fail при смене не делаем.
    """
    if not sidecar:
        return None
    saved = sidecar.get("n_envs")
    if saved is None:
        return None
    if int(saved) == int(n_envs):
        return None
    return (
        f"continue: n_envs sidecar={int(saved)} -> cli={int(n_envs)} "
        "(hardware; timesteps unchanged)"
    )


TrainModelMode = Literal["continue", "from_ancestor", "scratch"]


def _paths_same_zip(a: Path, b: Path) -> bool:
    return checkpoint_zip_path(a).resolve() == checkpoint_zip_path(b).resolve()


def resolve_train_model_mode(
    model_out: Path,
    model_in: Path | None,
    *,
    overwrite: bool = False,
) -> TrainModelMode:
    """Выбрать continue / from_ancestor / scratch или SystemExit при опасной комбинации.

    Не трогает файлы на диске — только читает ``is_file()``.
    """
    out = checkpoint_zip_path(model_out)
    out_exists = out.is_file()
    has_in = model_in is not None

    if has_in:
        assert model_in is not None
        in_path = checkpoint_zip_path(model_in)
        if not in_path.is_file():
            raise SystemExit(f"model-in not found: {in_path}")
        if _paths_same_zip(out, in_path):
            raise SystemExit(
                f"model-in and model-out are the same file ({out}). "
                "Omit --model-in to continue this generation."
            )
        if out_exists and not overwrite:
            raise SystemExit(
                f"model-out already exists: {out}. "
                "Omit --model-in to continue, choose another --model-out, "
                "or pass --overwrite-model-out to replace from --model-in."
            )
        return "from_ancestor"

    if out_exists and not overwrite:
        return "continue"

    if out_exists and overwrite:
        return "scratch"

    return "scratch"


def resolve_target_timesteps(cli_timesteps: int, sidecar: dict[str, Any] | None) -> int:
    """CLI может поднять target при continue; понижение sidecar не делается молча.

    Если CLI < sidecar target — оставляем sidecar (безопасный continue до прежней цели).
    Если CLI > sidecar — поднимаем цель (продолжить обучение / dual train+measure).
    """
    if not sidecar:
        return int(cli_timesteps)
    saved = int(sidecar.get("target_timesteps", cli_timesteps))
    cli = int(cli_timesteps)
    if cli > saved:
        return cli
    return saved


def atomic_save_model(model: PPO, checkpoint: Path) -> Path:
    """SB3 save через *.tmp.zip → rename."""
    out = checkpoint_zip_path(checkpoint)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp_zip = out.parent / f"{out.stem}.tmp"
    model.save(str(tmp_zip))
    if not tmp_zip.is_file():
        raise FileNotFoundError(f"expected SB3 checkpoint after save: {tmp_zip}")
    if out.is_file():
        out.unlink()
    tmp_zip.rename(out)
    return out


class LatestCheckpointCallback(BaseCallback):
    """on_rollout_end → models/latest.zip с throttling (H5).

    `every_rollouts=1` — каждый rollout (старое поведение).
    `every_rollouts=N` — каждый N-й (default train: 5 ≈ −15% wall vs каждый).
    """

    def __init__(
        self,
        latest_path: Path,
        *,
        every_rollouts: int = 1,
        verbose: int = 0,
    ):
        super().__init__(verbose)
        self._latest_path = checkpoint_zip_path(latest_path)
        self._every = max(int(every_rollouts), 1)
        self._rollout_idx = 0

    def _on_step(self) -> bool:
        return True

    def _on_rollout_end(self) -> bool:
        self._rollout_idx += 1
        if self._rollout_idx % self._every != 0:
            return True
        atomic_save_model(self.model, self._latest_path)
        if self.verbose:
            print(
                f"latest checkpoint -> {self._latest_path} "
                f"(rollout #{self._rollout_idx}, every={self._every})"
            )
        return True


class InterruptHandler:
    """KeyboardInterrupt и SIGTERM → единый флаг прерывания."""

    def __init__(self) -> None:
        self.interrupted = False
        self._previous: Any = None

    def __enter__(self) -> InterruptHandler:
        self._previous = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGTERM, self._handle)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        signal.signal(signal.SIGTERM, self._previous)
        if exc_type is KeyboardInterrupt:
            self.interrupted = True
            return True
        return False

    def _handle(self, signum: int, frame: Any) -> None:
        self.interrupted = True
        raise KeyboardInterrupt()
