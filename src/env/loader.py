"""Загрузка игрового env-пакета из games/<game_id>/env/."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import gymnasium as gym

from project_paths import game_dir, load_yaml


def import_game_env(game_id: str) -> ModuleType:
    """Импортирует games/<game_id>/env/ как Python-пакет."""
    meta = load_yaml(game_dir(game_id) / "game.yaml")
    pkg_name = meta.get("env_package", "env")
    pkg_dir = game_dir(game_id) / pkg_name
    init_py = pkg_dir / "__init__.py"
    if not init_py.is_file():
        raise FileNotFoundError(f"Game env package not found: {init_py}")

    module_name = f"wait_game_{game_id}_env"
    if module_name in sys.modules:
        return sys.modules[module_name]

    spec = importlib.util.spec_from_file_location(
        module_name,
        init_py,
        submodule_search_locations=[str(pkg_dir)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load env package: {pkg_dir}")

    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def make_env(
    game_id: str,
    mission_id: str | None = None,
    *,
    wrap_rewards: bool = True,
    **kwargs,
) -> gym.Env:
    """Фабрика: env из games/<game_id>/env/, mission из game.yaml если не задана."""
    meta = load_yaml(game_dir(game_id) / "game.yaml")
    mission = mission_id or meta.get("default_mission", "m1")
    mod = import_game_env(game_id)
    if not hasattr(mod, "make_env"):
        raise AttributeError(f"games/{game_id}/env/__init__.py must define make_env()")
    return mod.make_env(mission_id=mission, wrap_rewards=wrap_rewards, **kwargs)
