"""Tkinter GUI: Config / Inference / Train / Rollback + панель лога."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk
from typing import Any

from operator_launcher import catalog, commands, workspace
from operator_launcher.runner import ProcessRunner
from operator_launcher.train_log import TrainLogSpec, resolve_train_log_path, shell_with_tee
from project_paths import repo_root


class OperatorLauncherApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Operator Launcher")
        self.root.minsize(720, 560)

        self._job_active = False

        self._build_config_vars()
        self._build_inference_vars()
        self._build_train_vars()
        self._save_state_map: dict[str, str] = {}
        self._games = catalog.list_games()
        self._build_layout()
        self._runner = ProcessRunner(self._append_log)
        self._load_workspace_into_ui()
        self._on_game_changed()
        self._update_command_preview()
        self.root.after(120, self._poll_runner)

    # --- vars ---

    def _build_config_vars(self) -> None:
        self.var_game = tk.StringVar()
        self.var_mission = tk.StringVar()
        self.var_save_state = tk.StringVar()

    def _build_inference_vars(self) -> None:
        self.var_inf_mode = tk.StringVar(value="live")
        self.var_inf_model = tk.StringVar(value="gen0.zip")
        self.var_inf_stochastic = tk.BooleanVar(value=True)
        self.var_inf_max_steps = tk.IntVar(value=8000)
        self.var_inf_turbo = tk.BooleanVar(value=False)
        self.var_inf_reward = tk.StringVar(value="default")
        self.var_inf_episodes = tk.IntVar(value=5)
        self.var_inf_wipe = tk.BooleanVar(value=False)
        self.var_inf_input = tk.StringVar()
        self.var_inf_timeout = tk.DoubleVar(value=120.0)

    def _build_train_vars(self) -> None:
        self.var_train_mode = tk.StringVar(value="continue")
        self.var_train_model_out = tk.StringVar(value="gen0.zip")
        self.var_train_model_in = tk.StringVar(value="gen0.zip")
        self.var_train_timesteps = tk.IntVar(value=500_000)
        self.var_train_n_envs = tk.IntVar(value=6)
        self.var_train_bc_epochs = tk.IntVar(value=0)
        self.var_train_bc_demo = tk.StringVar(value="")
        self.var_train_reward = tk.StringVar(value="default")
        self.var_train_progress_pct = tk.BooleanVar(value=True)
        self.var_train_save_every = tk.IntVar(value=50_000)
        self.var_train_latest_model = tk.BooleanVar(value=True)
        self.var_train_latest_every = tk.IntVar(value=5)
        self.var_train_save_log = tk.BooleanVar(value=False)
        self.var_train_log_path = tk.StringVar(value="")

    # --- layout ---

    def _build_layout(self) -> None:
        self._notebook = ttk.Notebook(self.root)
        self._notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self._notebook.bind("<<NotebookTabChanged>>", lambda _e: self._update_command_preview())

        self._tab_config = ttk.Frame(self._notebook, padding=8)
        self._tab_inference = ttk.Frame(self._notebook, padding=8)
        self._tab_train = ttk.Frame(self._notebook, padding=8)
        self._tab_rollback = ttk.Frame(self._notebook, padding=8)
        self._notebook.add(self._tab_config, text="Config")
        self._notebook.add(self._tab_inference, text="Inference")
        self._notebook.add(self._tab_train, text="Train")
        self._notebook.add(self._tab_rollback, text="Rollback")

        self._build_command_preview()

        self._build_config_tab()
        self._build_inference_tab()
        self._build_train_tab()
        self._build_rollback_tab()
        self._wire_preview_traces()

        log_frame = ttk.LabelFrame(self.root, text="Лог", padding=4)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self._log = scrolledtext.ScrolledText(log_frame, height=14, state=tk.DISABLED, wrap=tk.WORD)
        self._log.pack(fill=tk.BOTH, expand=True)

    def _build_command_preview(self) -> None:
        cmd_frame = ttk.LabelFrame(self.root, text="Команда (копировать в терминал)", padding=4)
        cmd_frame.pack(fill=tk.X, padx=8, pady=(0, 4))
        cmd_inner = ttk.Frame(cmd_frame)
        cmd_inner.pack(fill=tk.X)
        self._cmd_preview = tk.Text(
            cmd_inner, height=3, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 9)
        )
        self._cmd_preview.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(cmd_inner, text="Копировать", command=self._copy_command).pack(
            side=tk.RIGHT, padx=(8, 0)
        )

    def _wire_preview_traces(self) -> None:
        traced: list[Any] = [
            self.var_inf_mode,
            self.var_inf_model,
            self.var_inf_stochastic,
            self.var_inf_max_steps,
            self.var_inf_turbo,
            self.var_inf_reward,
            self.var_inf_episodes,
            self.var_inf_wipe,
            self.var_inf_input,
            self.var_inf_timeout,
            self.var_train_mode,
            self.var_train_model_out,
            self.var_train_model_in,
            self.var_train_timesteps,
            self.var_train_n_envs,
            self.var_train_bc_epochs,
            self.var_train_bc_demo,
            self.var_train_reward,
            self.var_train_progress_pct,
            self.var_train_save_every,
            self.var_train_latest_model,
            self.var_train_latest_every,
            self.var_train_save_log,
            self.var_game,
            self.var_mission,
            self.var_save_state,
        ]
        for var in traced:
            var.trace_add("write", self._trace_preview)

    def _build_config_tab(self) -> None:
        frame = self._tab_config
        row = 0
        ttk.Label(frame, text="Игра").grid(row=row, column=0, sticky=tk.W, pady=2)
        self._combo_game = ttk.Combobox(
            frame, textvariable=self.var_game, state="readonly", width=48
        )
        self._combo_game.grid(row=row, column=1, sticky=tk.EW, pady=2)
        self._combo_game.bind("<<ComboboxSelected>>", lambda _e: self._on_game_changed())

        row += 1
        ttk.Label(frame, text="Миссия").grid(row=row, column=0, sticky=tk.W, pady=2)
        self._combo_mission = ttk.Combobox(
            frame, textvariable=self.var_mission, state="readonly", width=48
        )
        self._combo_mission.grid(row=row, column=1, sticky=tk.EW, pady=2)
        self._combo_mission.bind("<<ComboboxSelected>>", lambda _e: self._on_mission_changed())

        row += 1
        ttk.Label(frame, text="Чекпоинт миссии").grid(row=row, column=0, sticky=tk.W, pady=2)
        self._combo_save_state = ttk.Combobox(
            frame, textvariable=self.var_save_state, state="readonly", width=48
        )
        self._combo_save_state.grid(row=row, column=1, sticky=tk.EW, pady=2)

        row += 1
        ttk.Button(frame, text="Применить", command=self._apply_config).grid(
            row=row, column=1, sticky=tk.E, pady=8
        )
        frame.columnconfigure(1, weight=1)

    def _build_inference_tab(self) -> None:
        frame = self._tab_inference
        row = 0
        mode_frame = ttk.LabelFrame(frame, text="Режим", padding=6)
        mode_frame.grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=4)
        for idx, mode in enumerate(("live", "pool", "replay")):
            ttk.Radiobutton(
                mode_frame,
                text=mode,
                value=mode,
                variable=self.var_inf_mode,
                command=self._on_inference_mode_changed,
            ).grid(row=0, column=idx, padx=8)

        row += 1
        ttk.Label(frame, text="Модель").grid(row=row, column=0, sticky=tk.W)
        self._combo_inf_model = ttk.Combobox(frame, textvariable=self.var_inf_model, width=40)
        self._combo_inf_model.grid(row=row, column=1, sticky=tk.EW, pady=2)
        self._combo_inf_model.bind("<<ComboboxSelected>>", lambda _e: self._on_inf_model_changed())
        self._combo_inf_model.bind("<FocusOut>", lambda _e: self._on_inf_model_changed())

        row += 1
        self._inf_common = ttk.Frame(frame)
        self._inf_common.grid(row=row, column=0, columnspan=2, sticky=tk.EW)

        self._inf_live = ttk.LabelFrame(frame, text="Live", padding=6)
        self._inf_pool = ttk.LabelFrame(frame, text="Pool", padding=6)
        self._inf_replay = ttk.LabelFrame(frame, text="Replay", padding=6)

        self._build_inference_live_panel(self._inf_live)
        self._build_inference_pool_panel(self._inf_pool)
        self._build_inference_replay_panel(self._inf_replay)

        row += 1
        self._inf_live.grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=4)
        self._inf_pool.grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=4)
        self._inf_replay.grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=4)

        row += 1
        btn_row = ttk.Frame(frame)
        btn_row.grid(row=row, column=0, columnspan=2, sticky=tk.E, pady=8)
        self._btn_inf_start = ttk.Button(btn_row, text="Запустить / Собрать", command=self._start_inference)
        self._btn_inf_start.pack(side=tk.LEFT, padx=4)
        self._btn_inf_stop = ttk.Button(btn_row, text="Стоп", command=self._stop_process, state=tk.DISABLED)
        self._btn_inf_stop.pack(side=tk.LEFT, padx=4)

        frame.columnconfigure(1, weight=1)
        self._on_inference_mode_changed()

    def _build_inference_live_panel(self, parent: ttk.LabelFrame) -> None:
        ttk.Checkbutton(parent, text="stochastic", variable=self.var_inf_stochastic).grid(
            row=0, column=0, sticky=tk.W
        )
        ttk.Checkbutton(parent, text="turbo", variable=self.var_inf_turbo).grid(
            row=0, column=1, sticky=tk.W, padx=8
        )
        ttk.Label(parent, text="max_steps").grid(row=1, column=0, sticky=tk.W)
        ttk.Entry(parent, textvariable=self.var_inf_max_steps, width=10).grid(row=1, column=1, sticky=tk.W)
        ttk.Label(parent, text="reward_profile").grid(row=2, column=0, sticky=tk.W)
        self._combo_inf_reward = ttk.Combobox(parent, textvariable=self.var_inf_reward, width=24)
        self._combo_inf_reward.grid(row=2, column=1, sticky=tk.W)

    def _build_inference_pool_panel(self, parent: ttk.LabelFrame) -> None:
        ttk.Label(parent, text="episodes").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(parent, textvariable=self.var_inf_episodes, width=10).grid(row=0, column=1, sticky=tk.W)
        ttk.Checkbutton(parent, text="stochastic", variable=self.var_inf_stochastic).grid(
            row=1, column=0, sticky=tk.W
        )
        ttk.Label(parent, text="max_steps").grid(row=2, column=0, sticky=tk.W)
        ttk.Entry(parent, textvariable=self.var_inf_max_steps, width=10).grid(row=2, column=1, sticky=tk.W)
        ttk.Checkbutton(parent, text="wipe_gen_logs", variable=self.var_inf_wipe).grid(
            row=3, column=0, sticky=tk.W
        )
        ttk.Label(parent, text="reward_profile").grid(row=4, column=0, sticky=tk.W)
        self._combo_inf_pool_reward = ttk.Combobox(parent, textvariable=self.var_inf_reward, width=24)
        self._combo_inf_pool_reward.grid(row=4, column=1, sticky=tk.W)

    def _build_inference_replay_panel(self, parent: ttk.LabelFrame) -> None:
        ttk.Label(parent, text="input (.fm2)").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(parent, textvariable=self.var_inf_input, width=48).grid(row=0, column=1, sticky=tk.EW)
        ttk.Checkbutton(parent, text="turbo", variable=self.var_inf_turbo).grid(
            row=1, column=0, sticky=tk.W
        )
        ttk.Label(parent, text="timeout").grid(row=2, column=0, sticky=tk.W)
        ttk.Entry(parent, textvariable=self.var_inf_timeout, width=10).grid(row=2, column=1, sticky=tk.W)
        parent.columnconfigure(1, weight=1)

    def _build_train_tab(self) -> None:
        frame = self._tab_train
        row = 0
        ttk.Label(frame, text="train_mode").grid(row=row, column=0, sticky=tk.W)
        self._combo_train_mode = ttk.Combobox(
            frame,
            textvariable=self.var_train_mode,
            values=("continue", "scratch", "from_ancestor"),
            state="readonly",
            width=24,
        )
        self._combo_train_mode.grid(row=row, column=1, sticky=tk.W)
        self._combo_train_mode.bind("<<ComboboxSelected>>", lambda _e: self._on_train_mode_changed())

        fields: list[tuple[str, Any, str]] = [
            ("model_out", self.var_train_model_out, "combo"),
            ("model_in", self.var_train_model_in, "combo"),
            ("timesteps", self.var_train_timesteps, "entry"),
            ("n_envs", self.var_train_n_envs, "entry"),
            ("bc_epochs", self.var_train_bc_epochs, "entry"),
            ("reward_profile", self.var_train_reward, "combo_reward"),
            ("save_every", self.var_train_save_every, "entry"),
            ("latest_every", self.var_train_latest_every, "entry"),
        ]
        self._combo_train_model_out: ttk.Combobox | None = None
        self._combo_train_model_in: ttk.Combobox | None = None
        self._combo_train_reward: ttk.Combobox | None = None
        self._combo_train_bc_demo: ttk.Combobox | None = None

        for label, var, kind in fields:
            row += 1
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky=tk.W, pady=2)
            if kind == "entry":
                ttk.Entry(frame, textvariable=var, width=16).grid(row=row, column=1, sticky=tk.W)
            elif kind == "combo":
                combo = ttk.Combobox(frame, textvariable=var, width=32)
                combo.grid(row=row, column=1, sticky=tk.EW, pady=2)
                if label == "model_out":
                    self._combo_train_model_out = combo
                else:
                    self._combo_train_model_in = combo
            elif kind == "combo_reward":
                combo = ttk.Combobox(frame, textvariable=var, width=24)
                combo.grid(row=row, column=1, sticky=tk.W)
                self._combo_train_reward = combo

        row += 1
        ttk.Label(frame, text="bc_demo").grid(row=row, column=0, sticky=tk.W)
        self._combo_train_bc_demo = ttk.Combobox(frame, textvariable=self.var_train_bc_demo, width=48)
        self._combo_train_bc_demo.grid(row=row, column=1, sticky=tk.EW)

        row += 1
        flags = ttk.LabelFrame(frame, text="Логирование", padding=6)
        flags.grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=6)
        ttk.Checkbutton(flags, text="progress_pct", variable=self.var_train_progress_pct).grid(
            row=0, column=0, sticky=tk.W
        )
        ttk.Checkbutton(flags, text="latest_model", variable=self.var_train_latest_model).grid(
            row=1, column=0, sticky=tk.W
        )
        ttk.Checkbutton(
            flags, text="Сохранить лог (tmp/bench)", variable=self.var_train_save_log
        ).grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(4, 0))
        ttk.Label(flags, textvariable=self.var_train_log_path, wraplength=520).grid(
            row=3, column=0, columnspan=2, sticky=tk.W, pady=(2, 0)
        )

        row += 1
        btn_row = ttk.Frame(frame)
        btn_row.grid(row=row, column=0, columnspan=2, sticky=tk.E, pady=8)
        self._btn_train_start = ttk.Button(btn_row, text="Запустить", command=self._start_train)
        self._btn_train_start.pack(side=tk.LEFT, padx=4)
        self._btn_train_stop = ttk.Button(btn_row, text="Стоп", command=self._stop_process, state=tk.DISABLED)
        self._btn_train_stop.pack(side=tk.LEFT, padx=4)

        frame.columnconfigure(1, weight=1)
        self._on_train_mode_changed()

    def _build_rollback_tab(self) -> None:
        frame = self._tab_rollback
        ttk.Label(
            frame,
            text="Восстановить genN.zip из genN.prev.zip (без обучения). "
            "Снимок .prev создаётся перед continue/scratch.",
            wraplength=640,
        ).grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 8))

        ttk.Label(frame, text="model_out").grid(row=1, column=0, sticky=tk.W)
        self._combo_rollback_model_out = ttk.Combobox(
            frame, textvariable=self.var_train_model_out, width=32
        )
        self._combo_rollback_model_out.grid(row=1, column=1, sticky=tk.W, pady=2)

        btn_row = ttk.Frame(frame)
        btn_row.grid(row=2, column=0, columnspan=2, sticky=tk.E, pady=12)
        self._btn_rollback_run = ttk.Button(btn_row, text="Откатить", command=self._start_rollback)
        self._btn_rollback_run.pack(side=tk.LEFT, padx=4)
        self._btn_rollback_stop = ttk.Button(
            btn_row, text="Стоп", command=self._stop_process, state=tk.DISABLED
        )
        self._btn_rollback_stop.pack(side=tk.LEFT, padx=4)

        frame.columnconfigure(1, weight=1)

    # --- workspace / catalog ---

    def _load_workspace_into_ui(self) -> None:
        ws = workspace.load_operator_workspace()
        game_labels = [g.label for g in self._games]
        game_ids = [g.game_id for g in self._games]
        self._combo_game["values"] = game_labels
        self._game_id_by_label = {g.label: g.game_id for g in self._games}
        self._game_label_by_id = {g.game_id: g.label for g in self._games}

        game_id = ws["game"] if ws["game"] in game_ids else (game_ids[0] if game_ids else "")
        if game_id:
            self.var_game.set(self._game_label_by_id.get(game_id, game_id))
        self._populate_missions(game_id, ws.get("mission", ""))
        self._populate_save_states(game_id, self.var_mission.get(), ws.get("save_state", ""))
        self._refresh_model_lists(game_id, self.var_mission.get())

    def _current_game_id(self) -> str:
        label = self.var_game.get().strip()
        if hasattr(self, "_game_id_by_label"):
            return self._game_id_by_label.get(label, label)
        return label

    def _populate_missions(self, game_id: str, preferred: str = "") -> None:
        missions = catalog.list_missions(game_id) if game_id else []
        self._combo_mission["values"] = missions
        mission = preferred if preferred in missions else catalog.default_mission(game_id, preferred)
        if mission:
            self.var_mission.set(mission)

    def _populate_save_states(self, game_id: str, mission_id: str, preferred: str = "") -> None:
        entries = catalog.list_save_state_anchors(game_id, mission_id) if game_id and mission_id else []
        self._save_state_map = {e.display: e.rel_path for e in entries}
        displays = list(self._save_state_map.keys())
        self._combo_save_state["values"] = displays
        default_rel = catalog.default_save_state(game_id, mission_id, preferred)
        display = next((d for d, rel in self._save_state_map.items() if rel == default_rel), "")
        if not display and displays:
            display = displays[0]
        if display:
            self.var_save_state.set(display)

    def _refresh_model_lists(self, game_id: str, mission_id: str) -> None:
        models = catalog.list_model_zips(game_id, mission_id) if game_id and mission_id else []
        if not models:
            models = ["gen0.zip"]
        for combo in (
            self._combo_inf_model,
            self._combo_train_model_out,
            self._combo_train_model_in,
            self._combo_rollback_model_out,
        ):
            if combo is not None:
                combo["values"] = models
        if self.var_inf_model.get() not in models:
            self.var_inf_model.set(models[0])
        if self.var_train_model_out.get() not in models:
            self.var_train_model_out.set(models[0])
        if self.var_train_model_in.get() not in models:
            self.var_train_model_in.set(models[0])
        rewards = catalog.list_reward_profiles(game_id, mission_id)
        for combo in (self._combo_inf_reward, self._combo_inf_pool_reward, self._combo_train_reward):
            if combo is not None:
                combo["values"] = rewards
        if self.var_inf_reward.get() not in rewards:
            self.var_inf_reward.set("default" if "default" in rewards else rewards[0])
        if self.var_train_reward.get() not in rewards:
            self.var_train_reward.set("default" if "default" in rewards else rewards[0])
        demos = [""] + catalog.list_bc_demos(game_id, mission_id)
        if self._combo_train_bc_demo is not None:
            self._combo_train_bc_demo["values"] = demos
        self._on_inf_model_changed()
        self._update_command_preview()

    def _trace_preview(self, *_args: object) -> None:
        try:
            self._update_command_preview()
        except tk.TclError:
            self._set_command_preview("# …введите корректные числа в полях")

    def _bind_preview(self, widget: tk.Widget, sequence: str = "<KeyRelease>") -> None:
        widget.bind(sequence, lambda _e: self._update_command_preview())

    def _set_command_preview(self, text: str) -> None:
        preview = getattr(self, "_cmd_preview", None)
        if preview is None:
            return
        preview.configure(state=tk.NORMAL)
        preview.delete("1.0", tk.END)
        preview.insert("1.0", text)
        preview.configure(state=tk.DISABLED)

    def _copy_command(self) -> None:
        text = self._cmd_preview.get("1.0", tk.END).strip()
        if not text:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update_idletasks()

    def _active_tab_id(self) -> str:
        return self._notebook.tab(self._notebook.select(), "text")

    def _preview_argv(self) -> list[str] | list[list[str]] | None:
        try:
            tab = self._active_tab_id()
            if tab == "Config":
                return None
            game_id, mission_id, save_state = self._context()
            if tab == "Inference":
                mode = self.var_inf_mode.get()
                if mode == "live":
                    return commands.build_inference_live_phases(
                        game=game_id,
                        mission=mission_id,
                        save_state=save_state,
                        model=self.var_inf_model.get().strip(),
                        stochastic=bool(self.var_inf_stochastic.get()),
                        max_steps=self._var_int(self.var_inf_max_steps, 8000),
                        turbo=bool(self.var_inf_turbo.get()),
                        reward_profile=self.var_inf_reward.get().strip(),
                    )
                if mode == "pool":
                    return commands.build_inference_pool_phases(
                        game=game_id,
                        mission=mission_id,
                        save_state=save_state,
                        model=self.var_inf_model.get().strip(),
                        episodes=self._var_int(self.var_inf_episodes, 5),
                        stochastic=bool(self.var_inf_stochastic.get()),
                        max_steps=self._var_int(self.var_inf_max_steps, 8000),
                        wipe_gen_logs=bool(self.var_inf_wipe.get()),
                        reward_profile=self.var_inf_reward.get().strip(),
                    )
                return commands.build_inference_replay_argv(
                    game=game_id,
                    mission=mission_id,
                    input_path=self.var_inf_input.get().strip(),
                    turbo=bool(self.var_inf_turbo.get()),
                    timeout=self._var_float(self.var_inf_timeout, 120.0),
                )
            if tab == "Train":
                return commands.build_train_phases(
                    game=game_id,
                    mission=mission_id,
                    save_state=save_state,
                    train_mode=self.var_train_mode.get(),
                    model_out=self.var_train_model_out.get().strip(),
                    model_in=self.var_train_model_in.get().strip() or None,
                    timesteps=self._var_int(self.var_train_timesteps, 500_000),
                    n_envs=self._var_int(self.var_train_n_envs, 6),
                    bc_epochs=self._var_int(self.var_train_bc_epochs, 0),
                    bc_demo=self.var_train_bc_demo.get().strip() or None,
                    reward_profile=self.var_train_reward.get().strip(),
                    progress_pct=bool(self.var_train_progress_pct.get()),
                    save_every=self._var_int(self.var_train_save_every, 50_000),
                    latest_model=bool(self.var_train_latest_model.get()),
                    latest_every=self._var_int(self.var_train_latest_every, 5),
                )
            if tab == "Rollback":
                return commands.build_train_rollback_phases(
                    game=game_id,
                    mission=mission_id,
                    model_out=self.var_train_model_out.get().strip(),
                )
        except (ValueError, TypeError, tk.TclError):
            return None
        return None

    def _train_log_spec(self) -> TrainLogSpec:
        return TrainLogSpec(
            train_mode=self.var_train_mode.get(),
            model_out=self.var_train_model_out.get().strip(),
            model_in=self.var_train_model_in.get().strip() or None,
            timesteps=self._var_int(self.var_train_timesteps, 500_000),
            bc_epochs=self._var_int(self.var_train_bc_epochs, 0),
        )

    def _update_command_preview(self) -> None:
        tab = self._active_tab_id()
        if tab == "Config":
            self.var_train_log_path.set("")
            self._set_command_preview(
                "# Config: кнопка «Применить» сохраняет config/workspace.yaml (без subprocess)"
            )
            return
        argv = self._preview_argv()
        if argv is None:
            self.var_train_log_path.set("")
            self._set_command_preview("# Заполните обязательные поля (игра, миссия, чекпоинт)")
            return
        text = commands.format_argv_for_shell(argv)
        if tab == "Train":
            save_log = bool(self.var_train_save_log.get())
            if save_log:
                try:
                    log_path = resolve_train_log_path(self._train_log_spec())
                    rel = log_path.resolve().relative_to(repo_root().resolve())
                    self.var_train_log_path.set(rel.as_posix())
                    text = shell_with_tee(text, log_path, enabled=True)
                except (ValueError, TypeError, OSError):
                    self.var_train_log_path.set("")
            else:
                self.var_train_log_path.set("")
        else:
            self.var_train_log_path.set("")
        self._set_command_preview(text)

    def _on_game_changed(self) -> None:
        game_id = self._current_game_id()
        self._populate_missions(game_id)
        self._on_mission_changed()

    def _on_mission_changed(self) -> None:
        game_id = self._current_game_id()
        mission_id = self.var_mission.get().strip()
        self._populate_save_states(game_id, mission_id)
        self._refresh_model_lists(game_id, mission_id)

    def _on_inf_model_changed(self) -> None:
        game_id = self._current_game_id()
        mission_id = self.var_mission.get().strip()
        model = self.var_inf_model.get().strip() or "gen0.zip"
        self.var_inf_input.set(catalog.default_replay_input(game_id, mission_id, model))
        self._update_command_preview()

    def _context(self) -> tuple[str, str, str]:
        game_id = self._current_game_id()
        mission_id = self.var_mission.get().strip()
        save_display = self.var_save_state.get().strip()
        save_state = self._save_state_map.get(save_display, save_display)
        if not game_id or not mission_id:
            raise ValueError("Выберите игру и миссию")
        if not save_state:
            raise ValueError("Выберите чекпоинт миссии")
        return game_id, mission_id, save_state

    def _apply_config(self) -> None:
        try:
            game_id, mission_id, save_state = self._context()
        except ValueError as exc:
            messagebox.showerror("Config", str(exc))
            return
        workspace.save_operator_workspace(game_id, mission_id, save_state)
        self._append_log(f"[config] сохранено: {game_id} / {mission_id} / {save_state}\n")
        messagebox.showinfo("Config", "workspace.yaml обновлён")

    # --- inference / train mode UI ---

    def _on_inference_mode_changed(self) -> None:
        mode = self.var_inf_mode.get()
        self._inf_live.grid_remove()
        self._inf_pool.grid_remove()
        self._inf_replay.grid_remove()
        if mode == "live":
            self._inf_live.grid()
            self._btn_inf_start.configure(text="Запустить")
        elif mode == "pool":
            self._inf_pool.grid()
            self._btn_inf_start.configure(text="Собрать")
        else:
            self._inf_replay.grid()
            self._btn_inf_start.configure(text="Запустить")
        self._update_command_preview()

    def _on_train_mode_changed(self) -> None:
        mode = self.var_train_mode.get()
        if self._combo_train_model_in is not None:
            self._combo_train_model_in.configure(
                state="readonly" if mode == "from_ancestor" else tk.DISABLED
            )
        if not hasattr(self, "_runner") or not self._runner.running:
            self._btn_train_start.configure(state=tk.NORMAL)
        self._update_command_preview()

    # --- runner ---

    def _append_log(self, text: str) -> None:
        self._log.configure(state=tk.NORMAL)
        self._log.insert(tk.END, text)
        self._log.see(tk.END)
        self._log.configure(state=tk.DISABLED)

    def _set_running(self, running: bool) -> None:
        start_state = tk.DISABLED if running else tk.NORMAL
        self._btn_inf_start.configure(state=start_state)
        self._btn_inf_stop.configure(state=tk.NORMAL if running else tk.DISABLED)
        self._btn_train_start.configure(state=start_state)
        self._btn_train_stop.configure(state=tk.NORMAL if running else tk.DISABLED)
        self._btn_rollback_run.configure(state=start_state)
        self._btn_rollback_stop.configure(state=tk.NORMAL if running else tk.DISABLED)
        if not running:
            self._on_train_mode_changed()

    def _launch(
        self,
        argv: list[str] | list[list[str]],
        *,
        graceful_stop: bool = True,
        cleanup_fceux: bool = False,
        tee_path: Path | None = None,
    ) -> None:
        self._graceful_stop = graceful_stop
        self._cleanup_fceux = cleanup_fceux
        self._append_log(f"\n$ {commands.format_argv(argv)}\n")
        if tee_path is not None:
            try:
                rel = tee_path.resolve().relative_to(repo_root().resolve()).as_posix()
            except ValueError:
                rel = tee_path.as_posix()
            self._append_log(f"[tee] → {rel}\n")
        try:
            self._runner.start(argv, tee_path=tee_path)
        except Exception as exc:
            messagebox.showerror("Запуск", str(exc))
            return
        self._job_active = True
        self._set_running(True)

    def _finish_job(self) -> None:
        if self._runner.running:
            return
        code = self._runner.wait_done()
        if code is not None:
            self._append_log(f"[exit] код {code}\n")
        self._job_active = False
        self._set_running(False)

    def _stop_process(self) -> None:
        graceful = getattr(self, "_graceful_stop", True)
        cleanup = getattr(self, "_cleanup_fceux", True)
        self._runner.stop(graceful=graceful, cleanup_fceux=cleanup)
        self._append_log("[stop] остановка процесса…\n")
        self.root.after(200, self._finish_job)

    def _poll_runner(self) -> None:
        self._runner.pump()
        if self._job_active and not self._runner.running:
            self._finish_job()
        self.root.after(120, self._poll_runner)

    def _start_inference(self) -> None:
        if self._runner.running:
            return
        try:
            game_id, mission_id, save_state = self._context()
            mode = self.var_inf_mode.get()
            if mode == "live":
                argv = commands.build_inference_live_phases(
                    game=game_id,
                    mission=mission_id,
                    save_state=save_state,
                    model=self.var_inf_model.get().strip(),
                    stochastic=bool(self.var_inf_stochastic.get()),
                    max_steps=self._var_int(self.var_inf_max_steps, 8000),
                    turbo=bool(self.var_inf_turbo.get()),
                    reward_profile=self.var_inf_reward.get().strip(),
                )
                self._launch(argv, graceful_stop=False, cleanup_fceux=True)
            elif mode == "pool":
                argv = commands.build_inference_pool_phases(
                    game=game_id,
                    mission=mission_id,
                    save_state=save_state,
                    model=self.var_inf_model.get().strip(),
                    episodes=self._var_int(self.var_inf_episodes, 5),
                    stochastic=bool(self.var_inf_stochastic.get()),
                    max_steps=self._var_int(self.var_inf_max_steps, 8000),
                    wipe_gen_logs=bool(self.var_inf_wipe.get()),
                    reward_profile=self.var_inf_reward.get().strip(),
                )
                self._launch(argv, graceful_stop=False, cleanup_fceux=True)
            else:
                argv = commands.build_inference_replay_argv(
                    game=game_id,
                    mission=mission_id,
                    input_path=self.var_inf_input.get().strip(),
                    turbo=bool(self.var_inf_turbo.get()),
                    timeout=self._var_float(self.var_inf_timeout, 120.0),
                )
                self._launch(argv, graceful_stop=False, cleanup_fceux=True)
        except (ValueError, TypeError) as exc:
            messagebox.showerror("Inference", str(exc))
        except tk.TclError:
            messagebox.showerror("Inference", "Введите корректные числа в полях")

    def _start_train(self) -> None:
        if self._runner.running:
            return
        try:
            game_id, mission_id, save_state = self._context()
            bc_demo = self.var_train_bc_demo.get().strip() or None
            argv = commands.build_train_phases(
                game=game_id,
                mission=mission_id,
                save_state=save_state,
                train_mode=self.var_train_mode.get(),
                model_out=self.var_train_model_out.get().strip(),
                model_in=self.var_train_model_in.get().strip() or None,
                timesteps=self._var_int(self.var_train_timesteps, 500_000),
                n_envs=self._var_int(self.var_train_n_envs, 6),
                bc_epochs=self._var_int(self.var_train_bc_epochs, 0),
                bc_demo=bc_demo,
                reward_profile=self.var_train_reward.get().strip(),
                progress_pct=bool(self.var_train_progress_pct.get()),
                save_every=self._var_int(self.var_train_save_every, 50_000),
                latest_model=bool(self.var_train_latest_model.get()),
                latest_every=self._var_int(self.var_train_latest_every, 5),
            )
            tee_path = None
            if bool(self.var_train_save_log.get()):
                tee_path = resolve_train_log_path(self._train_log_spec())
                self.var_train_log_path.set(
                    tee_path.resolve().relative_to(repo_root().resolve()).as_posix()
                )
            self._launch(argv, graceful_stop=True, cleanup_fceux=True, tee_path=tee_path)
        except (ValueError, TypeError) as exc:
            messagebox.showerror("Train", str(exc))
        except tk.TclError:
            messagebox.showerror("Train", "Введите корректные числа в полях")

    def _start_rollback(self) -> None:
        if self._runner.running:
            return
        try:
            game_id, mission_id, _save_state = self._context()
            argv = commands.build_train_rollback_phases(
                game=game_id,
                mission=mission_id,
                model_out=self.var_train_model_out.get().strip(),
            )
            self._launch(argv, graceful_stop=False, cleanup_fceux=False)
        except (ValueError, TypeError) as exc:
            messagebox.showerror("Rollback", str(exc))

    @staticmethod
    def _var_int(var: tk.IntVar, default: int) -> int:
        try:
            return int(var.get())
        except (tk.TclError, ValueError, TypeError):
            return default

    @staticmethod
    def _var_float(var: tk.DoubleVar, default: float) -> float:
        try:
            return float(var.get())
        except (tk.TclError, ValueError, TypeError):
            return default

    @staticmethod
    def _optional_int(text: str) -> int | None:
        value = str(text).strip()
        if not value:
            return None
        return int(value)


def main() -> None:
    root = tk.Tk()
    OperatorLauncherApp(root)
    root.mainloop()
