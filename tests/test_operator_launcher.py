"""Тесты operator_launcher: argv без bash/WSL, runner stop, фазы."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from operator_launcher import commands, workspace  # noqa: E402
from operator_launcher.runner import ProcessRunner  # noqa: E402
from operator_launcher.train_log import (  # noqa: E402
    TrainLogSpec,
    build_train_log_basename,
    resolve_train_log_path,
    sanitize_token,
    shell_with_tee,
)


def _is_venv_python(path: str) -> bool:
    norm = path.replace("\\", "/").lower()
    return norm.endswith("/.venv/scripts/python.exe") or norm.endswith("/.venv/bin/python")


def test_inference_live_phases_use_venv_python_not_bash():
    phases = commands.build_inference_live_phases(
        game="rushn_attack",
        mission="m1",
        save_state="save_states/cp_gameplay0.fc0",
        model="gen0.zip",
        stochastic=True,
        max_steps=100,
        turbo=False,
        reward_profile="default",
    )
    assert len(phases) == 2
    for phase in phases:
        assert _is_venv_python(phase[0])
        assert "bash" not in phase
    assert phases[0][1] == "scripts/inference_preflight.py"
    assert phases[1][1] == "src/stream/run_inference.py"
    assert "--live" in phases[1]
    assert "--skip-preflight" in phases[1]


def test_inference_pool_phases_preflight_wipe_flag():
    phases = commands.build_inference_pool_phases(
        game="rushn_attack",
        mission="m1",
        save_state="save_states/cp_gameplay0.fc0",
        model="gen0.zip",
        playlist_cnt=2,
        stochastic=True,
        max_steps=100,
        wipe_gen_logs=True,
        playlist_no_dedupe=False,
        reward_profile="default",
    )
    assert "--wipe-gen-logs" in phases[0]
    assert "--playlist-cnt" in phases[1]


def _train_phases_kwargs(**overrides):
    base = {
        "game": "rushn_attack",
        "mission": "m1",
        "save_state": "save_states/cp_gameplay0.fc0",
        "train_mode": "continue",
        "model_out": "gen0.zip",
        "model_in": None,
        "timesteps": 1000,
        "n_envs": 2,
        "bc_epochs": 0,
        "bc_demo": None,
        "reward_profile": "default",
        "progress_pct": True,
        "save_every": 500,
        "latest_model": True,
        "latest_every": 5,
    }
    base.update(overrides)
    return base


def test_train_phases_structure():
    phases = commands.build_train_phases(**_train_phases_kwargs())
    assert phases[0][1] == "scripts/train_preflight.py"
    assert phases[1][1] == "src/train/train_ppo.py"
    assert "--n-envs" in phases[1] and "2" in phases[1]


def test_train_phases_bc_requires_demo():
    with pytest.raises(ValueError, match="bc_demo"):
        commands.build_train_phases(**_train_phases_kwargs(bc_epochs=5, bc_demo=None))
    with pytest.raises(ValueError, match="bc_demo"):
        commands.build_train_phases(**_train_phases_kwargs(bc_epochs=5, bc_demo="   "))

    demo = "reference/demos_for_bc/seg_002.npz"
    phases = commands.build_train_phases(**_train_phases_kwargs(bc_epochs=5, bc_demo=demo))
    train_argv = phases[1]
    assert "--bc-epochs" in train_argv
    assert "5" in train_argv
    assert "--bc-demo" in train_argv
    assert demo in train_argv


def test_train_rollback_phases_no_save_state():
    phases = commands.build_train_rollback_phases(
        game="rushn_attack",
        mission="m1",
        model_out="gen0.zip",
    )
    flat = " ".join(phases[1])
    assert "--rollback" in flat
    assert "--save-state" not in flat


def test_replay_argv_uses_python():
    argv = commands.build_inference_replay_argv(
        game="rushn_attack",
        mission="m1",
        input_path="logs/gen0/playlist.json",
        turbo=False,
        timeout=10.0,
    )
    assert _is_venv_python(argv[0])
    assert argv[1] == "scripts/play_inference_fm2.py"


def test_workspace_roundtrip(tmp_path):
    path = tmp_path / "workspace.yaml"
    workspace.save_operator_workspace("g1", "m1", "save_states/x.fc0", path=path)
    loaded = workspace.load_operator_workspace(path)
    assert loaded == {"game": "g1", "mission": "m1", "save_state": "save_states/x.fc0"}


def test_runner_stop_kills_sleeping_process():
    lines: list[str] = []
    runner = ProcessRunner(lines.append)
    runner.start([sys.executable, "-c", "import time; time.sleep(60)"])
    time.sleep(0.4)
    assert runner.running
    runner.stop(graceful=False, cleanup_fceux=False)
    code = runner.wait_done()
    assert not runner.running
    assert code is not None


def test_runner_runs_phases_in_order():
    lines: list[str] = []
    runner = ProcessRunner(lines.append)
    phases = [
        [sys.executable, "-c", "print('phase1', flush=True)"],
        [sys.executable, "-c", "print('phase2', flush=True)"],
    ]
    runner.start(phases)
    deadline = time.time() + 5
    while runner.running and time.time() < deadline:
        runner.pump()
        time.sleep(0.05)
    code = runner.wait_done()
    assert code == 0
    joined = "".join(lines)
    assert "phase1" in joined
    assert "phase2" in joined


def test_format_argv_for_shell_single_phase():
    argv = commands.build_inference_replay_argv(
        game="rushn_attack",
        mission="m1",
        input_path="logs/gen0/playlist.json",
        turbo=False,
        timeout=10.0,
    )
    text = commands.format_argv_for_shell(argv)
    assert text.startswith(".venv/Scripts/python.exe")
    assert "play_inference_fm2.py" in text
    assert "bash" not in text


def test_format_argv_for_shell_multiphase():
    phases = commands.build_inference_live_phases(
        game="rushn_attack",
        mission="m1",
        save_state="save_states/cp_gameplay0.fc0",
        model="gen0.zip",
        stochastic=True,
        max_steps=100,
        turbo=False,
        reward_profile="default",
    )
    text = commands.format_argv_for_shell(phases)
    assert " && " in text
    assert text.count(".venv/Scripts/python.exe") == 2


def test_gui_app_initializes():
    import tkinter as tk

    from operator_launcher.app import OperatorLauncherApp

    root = tk.Tk()
    root.withdraw()
    try:
        app = OperatorLauncherApp(root)
        assert app._cmd_preview is not None
        assert app._log is not None
        assert app._runner is not None
        assert app._cmd_preview.get("1.0", "end").strip()
    finally:
        root.destroy()


def test_var_int_handles_invalid_intvar():
    import tkinter as tk

    from operator_launcher.app import OperatorLauncherApp

    root = tk.Tk()
    root.withdraw()
    try:
        var = tk.IntVar(value=6)
        var.set("")
        assert OperatorLauncherApp._var_int(var, 6) == 6
    finally:
        root.destroy()


def test_var_int_empty_entry_does_not_crash_preview():
    import tkinter as tk

    from operator_launcher.app import OperatorLauncherApp

    root = tk.Tk()
    root.withdraw()
    try:
        app = OperatorLauncherApp(root)
        app._notebook.select(app._tab_train)
        app.var_train_n_envs.set("")
        app._update_command_preview()
        text = app._cmd_preview.get("1.0", "end")
        assert "python" in text.lower() or text.strip().startswith("#")
    finally:
        root.destroy()


def test_inference_preflight_argv_matches_facade():
    phases = commands.build_inference_live_phases(
        game="rushn_attack",
        mission="m1",
        save_state="save_states/cp_gameplay0.fc0",
        model="gen0.zip",
        stochastic=True,
        max_steps=50,
        turbo=False,
        reward_profile="default",
    )
    pre = phases[0]
    assert pre[2:6] == ["--game", "rushn_attack", "--mission", "m1"]
    assert pre[pre.index("--model") + 1] == "gen0.zip"


def test_sanitize_token():
    assert sanitize_token("gen0.zip") == "gen0"
    assert sanitize_token("--bc-epochs 5") == "bc-epochs_5"
    assert sanitize_token("from_ancestor") == "from_ancestor"
    assert sanitize_token("path/with spaces") == "path_with_spaces"
    assert sanitize_token("") == "x"


def test_build_train_log_basename():
    from datetime import datetime

    spec = TrainLogSpec(
        train_mode="continue",
        model_out="gen0.zip",
        model_in=None,
        timesteps=500_000,
        bc_epochs=5,
    )
    name = build_train_log_basename(spec, now=datetime(2026, 1, 1, 12, 0, 0))
    assert name == "20260101_120000_gen0_continue_bc_epochs_5_500000.log"

    scratch = TrainLogSpec(
        train_mode="scratch",
        model_out="gen0.zip",
        model_in=None,
        timesteps=50_000,
        bc_epochs=0,
    )
    assert build_train_log_basename(scratch, now=datetime(2026, 1, 1, 12, 0, 0)) == (
        "20260101_120000_gen0_scratch_50000.log"
    )

    ancestor = TrainLogSpec(
        train_mode="from_ancestor",
        model_out="gen1.zip",
        model_in="gen0.zip",
        timesteps=10_000,
        bc_epochs=0,
    )
    assert build_train_log_basename(ancestor, now=datetime(2026, 1, 1, 12, 0, 0)) == (
        "20260101_120000_gen1_from_ancestor_gen0_10000.log"
    )


def test_resolve_train_log_path(tmp_path):
    from datetime import datetime

    spec = TrainLogSpec(
        train_mode="continue",
        model_out="gen0.zip",
        model_in=None,
        timesteps=1000,
        bc_epochs=0,
    )
    path = resolve_train_log_path(spec, bench_dir=tmp_path, now=datetime(2026, 8, 4, 9, 30, 0))
    assert path.parent == tmp_path
    assert path.name == "20260804_093000_gen0_continue_1000.log"
    assert tmp_path.is_dir()


def test_shell_with_tee_wraps_subshell(tmp_path):
    log_path = tmp_path / "run.log"
    cmd = ".venv/Scripts/python.exe scripts/train_preflight.py"
    assert shell_with_tee(cmd, log_path, enabled=False) == cmd
    wrapped = shell_with_tee(cmd, log_path, enabled=True)
    assert wrapped.startswith("{ ")
    assert wrapped.endswith(f"; }} 2>&1 | tee {log_path.as_posix()}") or "2>&1 | tee " in wrapped


def test_runner_writes_tee_file(tmp_path):
    lines: list[str] = []
    tee = tmp_path / "out.log"
    runner = ProcessRunner(lines.append)
    runner.start([sys.executable, "-c", "print('hello_tee', flush=True)"], tee_path=tee)
    deadline = time.time() + 5
    while runner.running and time.time() < deadline:
        runner.pump()
        time.sleep(0.05)
    code = runner.wait_done()
    assert code == 0
    assert "hello_tee" in "".join(lines)
    assert "hello_tee" in tee.read_text(encoding="utf-8")

