# SCRIPTS — консольные скрипты wait/

> Запуск из корня репозитория: `D:\wait\`  
> Python-скрипты: активировать `.venv` или использовать `.venv\Scripts\python.exe`

---

## Установка окружения

| Скрипт | Назначение |
| ------ | ---------- |
| [`scripts/setup_venv.ps1`](../scripts/setup_venv.ps1) | Создаёт `.venv`, ставит `requirements.txt` |
| [`scripts/setup_all.ps1`](../scripts/setup_all.ps1) | `setup_venv` (FCEUX — вручную в `fceux/portable/`) |
| [`scripts/verify_env.py`](../scripts/verify_env.py) | Проверка импортов ML-стека |

```powershell
.\scripts\setup_all.ps1
.\.venv\Scripts\python.exe scripts\verify_env.py
```

---

## Эталон и RAM

| Скрипт | Вход | Выход |
| ------ | ---- | ----- |
| [`scripts/ram_scout.py`](../scripts/ram_scout.py) | FM2 в `reference/` | `reference/scout/ram_scout.jsonl`, `config/ram_resolve.json`, `ram_map.md` |
| [`scripts/build_playthrough.py`](../scripts/build_playthrough.py) | FM2 + `reference/scout/ram_scout.jsonl` | `human_playthrough.jsonl`, `config/`, `states/cp*.fc0`, `demos/` |
| [`scripts/build_inference_states.py`](../scripts/build_inference_states.py) | FM2 + `human_playthrough.jsonl` | `states/inference_cp0.fc0`, блок `inference` в manifest |
| [`scripts/segment_playthrough.py`](../scripts/segment_playthrough.py) | manifest + human jsonl | `demos/seg_*.npz` (actions only, obs=stub) |
| [`scripts/record_demos.py`](../scripts/record_demos.py) | manifest + human jsonl + env | `demos/seg_*.npz` (реальные obs для BC) |

### RAM scout

```bash
./.venv/Scripts/python.exe scripts/ram_scout.py games/rushn_attack/missions/m1/reference/clear.fm2
```

1. Положите `.fm2` в `games/<game>/missions/<m>/reference/`
2. FCEUX → `reference/scout/ram_scout.jsonl` → авто-resolve → `config/ram_resolve.json`, `ram_map.md`

| Аргумент / флаг | Описание |
| --------------- | -------- |
| `fm2` (позиционный) | путь к FM2 |
| `--timeout` | лимит секунд (FCEUX) |
| `--no-ram-map` | не обновлять `ram_map.md` |

### Эталон (после ram_scout)

```bash
./.venv/Scripts/python.exe scripts/build_playthrough.py games/rushn_attack/missions/m1/reference/clear.fm2
```

Создаёт `reference/human_playthrough.jsonl`, `config/routes.yaml`, `config/playthrough_manifest.yaml` (в т.ч. `inference.gameplay_start_frame`), save states **train** `states/cp0..cpN.fc0` (кадр 1 сегмента = intro для seg_001), demos в `demos/`.

**Train vs inference save state:** `cp0.fc0` — reset env/train по manifest (кадр 1 эталона); `inference_cp0.fc0` — старт gameplay (первый кадр вне intro), для `run_inference.py` / эфира. Пересборка inference state:

```bash
./.venv/Scripts/python.exe scripts/build_inference_states.py games/rushn_attack/missions/m1/reference/clear.fm2
```

| Флаг | Описание |
| ---- | -------- |
| `--skip-states` | без save states train (`cp*.fc0`) |
| `--skip-inference-states` | без `inference_cp0.fc0` (если `--skip-states` не задан) |
| `--skip-demos` | без `demos/seg_*.npz` |

### Demos с реальными obs (BC)

После Phase 1 env — пересборка `demos/seg_*.npz` с кадрами из FCEUX (тот же pipeline, что train/inference):

```bash
./.venv/Scripts/python.exe scripts/record_demos.py games/rushn_attack/missions/m1/reference/clear.fm2
```

По умолчанию сегменты пишутся **параллельно** (`min(segments, cpu, 8)` процессов FCEUX — см. ML_CONCEPT §2).

Один сегмент / отладка:

```bash
./.venv/Scripts/python.exe scripts/record_demos.py games/rushn_attack/missions/m1/reference/clear.fm2 --segment seg_001 --max-steps 20 --jobs 1
```

| Аргумент / флаг | Описание |
| --------------- | -------- |
| `fm2` (позиционный) | путь к FM2 (определение миссии) |
| `--segment ID` | только `seg_001` и т.д. (можно несколько раз) |
| `--max-steps` | лимит env steps на сегмент (отладка) |
| `--jobs` | parallel FCEUX (default `min(segments, cpu, 8)`; `1` = последовательно) |
| `--session` | id сессии FCEUX bridge (default `record_demos`) |
| `--no-turbo` | без turbo (медленнее, стабильнее) |

Выход: `demos/seg_*.npz` с `obs` `(N, 4, 84, 84)` float32, `actions` int64, `meta.obs_stub: false`.  
`N` ≈ число NES-кадров сегмента / `frame_skip` (4). Нужен для `--bc-epochs` в `train_ppo.py`.

---

## Phase 1 — bridge

### Smoke (единый entry point, BACKLOG 4.1)

```bash
./.venv/Scripts/python.exe scripts/run_smoke.py
./.venv/Scripts/python.exe scripts/run_smoke.py --suite bridge,env,parallel
```

| Аргумент | Описание |
| -------- | -------- |
| `--suite` | подмножество: `bridge`, `env`, `parallel` (default — все три) |

Subprocess: `smoke_bridge.py`; `smoke_env.py --steps 20`; `test_parallel_env.py --n-envs 8 --cycles 10 --reset-every 5`. В `finally`: `cleanup_bridge_sessions`, `cleanup_artifact_quarantine("smoke")`, проверка stray `smoke_*` в checkpoints. Exit code 0/1.

**Pytest (BACKLOG 4.3):** то же покрытие + autouse cleanup в `tests/conftest.py`.

```bash
./.venv/Scripts/pip.exe install pytest   # или pip install -r requirements.txt
./.venv/Scripts/python.exe -m pytest tests/smoke/ -v
./.venv/Scripts/python.exe -m pytest tests/smoke/ -m requires_fceux
```

Интеграционные тесты помечены `@pytest.mark.requires_fceux` (skip без бинарника FCEUX).

После правок bridge/env — **`run_smoke.py`** или **`pytest tests/smoke/`**, не короткий `train_ppo`.

| Скрипт | Вход | Выход |
| ------ | ---- | ----- |
| [`scripts/run_smoke.py`](../scripts/run_smoke.py) | `--suite` | stdout; exit 0/1 |
| [`scripts/smoke_bridge.py`](../scripts/smoke_bridge.py) | `states/cp1.fc0` (после `build_playthrough.py`) | stdout: PING, RAM, OBS, turbo |

```bash
./.venv/Scripts/python.exe scripts/smoke_bridge.py
```

Smoke-тест IPC Python ↔ FCEUX (`FceuxBridge`): load state, ping, step, RAM, obs 84×84, turbo.

**1.6 (2026-07-07):** hot reset — один IPC `LOAD_OBS`; `POLL_INTERVAL=2ms`. ms/hot reset **−21% / −34%** vs 1.5.

**Train no-focus (этап 1.2):** при `fceux/profiles/train.yaml` → `no_focus: true` или `WAIT_FCEUX_NO_FOCUS=1` окна FCEUX стартуют свёрнутыми (`STARTUPINFO` / `SW_SHOWMINNOACTIVE`), на первом кадре Lua `winapi` дополнительно minimize/off-screen; опционально `-bginput 1`. Отключить: `WAIT_FCEUX_NO_FOCUS=0`. **Не** применяется к inference (`show_window=True`). Гарантия «фокус не уходит» на Windows не 100% — только train/bridge headless.

**Train fast obs (этап 1.7):** `train.yaml` → `obs_format: raw` (default для headless train); override `WAIT_FCEUX_OBS_FORMAT=gd`. Inference остаётся на `gd`.

**IPC v2 PoC (этап 1.8, опционально):** `WAIT_FCEUX_IPC=v2` — бинарный length-prefix (`request.v2`/`response.v2`, magic `WQST`/`WAIT`) + obs inline в ответе (без `obs_*.raw`). **По умолчанию v1** — v2 медленнее на Windows (см. benchmark). Протокол: `src/bridge_ipc.py`. `train_local.sh` и `fceux/profiles/train.yaml` фиксируют **v1**.

### Train defaults (проверено 1.1–1.8)

Единый стек без известных проблем на Windows (i7-3770, 8 env):

| Параметр | Значение | Где задано |
| -------- | -------- | ---------- |
| IPC transport | **v1** (JSON + `obs_*.raw`) | `train.yaml`, `WAIT_FCEUX_IPC`, `train_local.sh` |
| obs format | **raw** 84×84 | `train.yaml`, `WAIT_FCEUX_OBS_FORMAT` |
| no-focus | **on** | `train.yaml`, `WAIT_FCEUX_NO_FOCUS` |
| frame_skip | **4** | `train.yaml`, env default |
| n_envs | **8** | `train_ppo.py` |
| torch threads | **2** | `train_ppo.py` |
| PPO n_steps / batch | **128 / 256** | `train_ppo.py` |
| turbo (FCEUX) | **on** | env default (`--no-turbo` для отладки) |

**Не использовать в train:** `WAIT_FCEUX_IPC=v2` (медленнее, нестабилен при n_envs>1). Inference: `obs_format: gd`, `ipc_transport: v1` (`inference.yaml`).

**Гигиена:** smoke не пишет в `games/.../checkpoints/`; карантин — `tmp/smoke/` ([DESIGN.md](DESIGN.md#гигиена-артефактов)). После правок bridge/env — эти скрипты, не короткий `train_ppo`.

| Аргумент / флаг | Описание |
| --------------- | -------- |
| `fm2` (опционально) | путь к FM2 для определения миссии; по умолчанию `games/rushn_attack/missions/m1/reference/clear.fm2` |

### IPC benchmark (baseline, этап 1.5)

```bash
./.venv/Scripts/python.exe scripts/benchmark_bridge.py --n-envs 1
./.venv/Scripts/python.exe scripts/benchmark_bridge.py --n-envs 8
./.venv/Scripts/python.exe scripts/benchmark_bridge.py --ipc v2 --n-envs 1   # PoC v2
```

JSON-отчёт: `tmp/bench/bridge_baseline/baseline_report.json` (или `--json-out`).

**Baseline (i7-3770, Win10 19045, 2026-07-07, `frame_skip=4`, train no-focus on):**

| Режим | ms/step | ms/hot reset | env-steps/s (1 proc) | env-steps/s (parallel) | reset/step |
| ----- | ------- | ------------ | -------------------- | ---------------------- | ---------- |
| n_envs=1 (1.5) | 28.6 | 41.5 | **35.0** | — | 1.45 |
| n_envs=8 (1.5) | 27.7 | 43.5 | **36.1** | **19.5** (8×15 steps) | 1.57 |
| n_envs=1 (**1.6**) | 29.7 | **32.7** | 33.6 | — | 1.10 |
| n_envs=8 (**1.6**) | 28.0 | **28.8** | 35.8 | 18.9 | 1.03 |
| n_envs=1 (**1.7 raw**) | **24.0** | 27.2 | **41.7** | — | 1.14 |
| n_envs=8 (**1.7 raw**) | **13.8** | **14.6** | **72.5** | **21.1** | 1.06 |
| n_envs=1 (**1.8 v1**, повтор) | 16.6 | 16.4 | 60.2 | — | 0.99 |
| n_envs=8 (**1.8 v1**, повтор) | 22.4 | 21.7 | 44.6 | **21.9** | 0.97 |
| n_envs=1 (**1.8 v2** PoC) | 26.7 | 26.8 | 37.5 | — | 1.00 |

**1.7 (2026-07-07):** train `obs_format: raw` — downscale/grayscale в Lua → `obs_*.raw` (7 KB); Python без cv2; STEP без лишнего `frameadvance`. ms/step **−16% / −50%** vs 1.5; decode ~0.3 ms.

**1.8 (2026-07-07):** FCEUX Lua без socket/pipe — PoC «v2» = один бинарный response с inline obs. **Не включаем по умолчанию:** ms/step n=1 **+61%** vs v1 (16.6→26.7); parallel n=8 v2 нестабилен. Named pipes / shared memory потребуют native DLL или внешний proxy — ROI не оправдан после 1.7 (~21 env-steps/s).

Исторический end-to-end train до baseline: ~**0.5 env-step/s** (4 env, BACKLOG) vs ~**1.9** (train-smoke dummy-vec) vs ~**20** (parallel step-only, 8 proc) — разрыв из‑за PPO, `bridge_load_lock` на reset и коротких эпизодов.

**E2E train после 1.9 (i7-3770, Win10 19045, 2026-07-09, `n_envs=8`, `frame_skip=4`, `ep_len_mean≈2`):**

| Метрика | env-steps/s | Методика |
| ------- | ----------- | -------- |
| bridge step-only parallel (1.7–1.8) | **~22** | `benchmark_bridge.py --n-envs 8` (таблица выше) |
| bridge step-only 1 proc (регрессия 1.9) | **~38** | `benchmark_bridge.py --n-envs 1`, 2026-07-09 |
| **e2e PPO wall** | **~5.0** | `benchmark_train.py --mode gate`; cold start 8 FCEUX в rollout 1 |
| **e2e PPO steady** | **~5.9** | rollout 2+ (`--warmup-rollouts 1`) |
| e2e PPO (SB3 `time/fps`) | **4–5** | `train_ppo.py --n-envs 8 --timesteps 2048` |
| historical pre-1.x | **~0.5** | 4 env, до IPC-оптимизаций |

**Вывод:** e2e **~10×** исторического ~0.5 (wall); **~0.21×** bridge parallel step-only — узкое место PPO update + reset storm при `ep_len≈2`, не raw STEP IPC. Перед длинным train: `cleanup_bridge_sessions` / нет зависших `fceux64.exe`.

Отчёты: `tmp/bench/train_e2e_gate/train_report.json`, checkpoint smoke: `tmp/bench/train_smoke_gate/`.

| Аргумент | Описание |
| -------- | -------- |
| `--n-envs` | parallel FCEUX для aggregate throughput (default 8) |
| `--step-samples` | число STEP замеров (default 30) |
| `--reset-samples` | число hot reset замеров (default 10) |
| `--parallel-steps` | steps на env в parallel-фазе (default 20) |
| `--ipc` | `v1` (default) или `v2` (PoC binary inline obs; env `WAIT_FCEUX_IPC`) |

### E2E train benchmark (BACKLOG 1.9)

```bash
./.venv/Scripts/python.exe scripts/benchmark_train.py --dry-run
./.venv/Scripts/python.exe scripts/benchmark_train.py --mode gate    # 2048 timesteps, фаза C gate
./.venv/Scripts/python.exe scripts/benchmark_train.py --mode fps     # 8192 timesteps, steady fps
```

JSON + checkpoint: `tmp/bench/train_e2e/` (`train_report.json`, `bench_train.zip`) — **не** `games/.../checkpoints/`.

| Аргумент | Описание |
| -------- | -------- |
| `--mode gate\|fps\|custom` | gate=2048 steps; fps=8192; custom=--timesteps |
| `--timesteps` | override режима |
| `--n-envs` | SubprocVecEnv (default 8) |
| `--warmup-rollouts` | rollout'ы вне steady fps (default 1) |
| `--session` | подкаталог `tmp/bench/<session>/` |
| `--bridge-report` | JSON `benchmark_bridge` для сравнения |
| `--dry-run` | только пути, без `learn` |

Метрики: `env_steps/s (wall)` — полный wall-clock; `env_steps/s (steady)` — после `--warmup-rollouts`. Сравнение с `benchmark_bridge.py` parallel и историческим ~0.5 env-step/s (4 env, pre-1.x). См. таблицу **E2E train после 1.9** в секции IPC benchmark выше.

**train-smoke (фаза C):**

```bash
./.venv/Scripts/python.exe src/train/train_ppo.py --n-envs 8 --timesteps 2048 --no-resume --no-bc \
  --checkpoint-out "$(pwd)/tmp/bench/train_smoke_gate/train_smoke.zip" --no-progress-pct
```

### Gymnasium env

| Скрипт | Вход | Выход |
| ------ | ---- | ----- |
| [`scripts/smoke_env.py`](../scripts/smoke_env.py) | `states/cp1.fc0`, `config/routes.yaml` | stdout: obs, reward, max_cp; опц. `logs/YYYYMMDD_attempts.jsonl` |

```bash
./.venv/Scripts/python.exe scripts/smoke_env.py --steps 100 --log
```

Random agent: `make_env(game_id)` → `games/<game>/env/` + `CheckpointRewardWrapper`.

| Аргумент / флаг | Описание |
| --------------- | -------- |
| `--steps` | число шагов (по умолчанию 100) |
| `--save-state` | save state относительно миссии (по умолчанию `states/cp1.fc0`) |
| `--session` | id сессии FCEUX bridge (по умолчанию `smoke_env`) |
| `--log` | дописать эпизод в `logs/YYYYMMDD_attempts.jsonl` |

**Parallel IPC stress (BACKLOG 1.9 tier 1):** [`scripts/test_parallel_env.py`](../scripts/test_parallel_env.py) — `SubprocVecEnv`, 8 env, циклы step + периодический `reset` (без PPO).

```bash
./.venv/Scripts/python.exe scripts/test_parallel_env.py --n-envs 8 --cycles 30 --reset-every 5
```

| Аргумент | Описание |
| -------- | -------- |
| `--n-envs` | parallel env (default 8) |
| `--cycles` | раундов step на все env (default 30) |
| `--reset-every` | принудительный `vec.reset()` каждые N циклов (default 5; 0 = только initial) |

---

## Phase 2 — обучение и inference

| Скрипт | Вход | Выход |
| ------ | ---- | ----- |
| [`src/train/train_ppo.py`](../src/train/train_ppo.py) | env + опц. `tasks/train_task.json` | `checkpoints/m1_vN.zip`, промежуточные в `checkpoints/runs/` |
| [`src/train/bc_pretrain.py`](../src/train/bc_pretrain.py) | `demos/seg_*.npz` (реальные obs) | warm-start policy (вызывается из train_ppo) |
| [`scripts/train_local.sh`](../scripts/train_local.sh) | task JSON или CLI | запуск train_ppo |
| [`src/stream/run_inference.py`](../src/stream/run_inference.py) | checkpoint `.zip` | `logs/YYYYMMDD_attempts.jsonl`, `logs/YYYYMMDD_inference_inputs.jsonl`, опц. FM2 / плейлист |
| [`scripts/export_fm2.py`](../scripts/export_fm2.py) | `inference_inputs.jsonl` | `.fm2` (без `reference/`) |
| [`scripts/eval_achievements.py`](../scripts/eval_achievements.py) | `attempts.jsonl` + `config/achievements.yaml` | `tags[]` в attempts |
| [`scripts/build_playlist.py`](../scripts/build_playlist.py) | attempts + опц. inference_inputs | FM2 по номинациям, `playlist.json` |

### Первая модель (v0)

```bash
# 8 parallel env (default на i7-3770), 500k steps (~1–3 суток)
./scripts/train_local.sh --timesteps 500000 --checkpoint-out checkpoints/m1_v0.zip

# отладка train: карантин tmp/smoke (не checkpoints/smoke_* в games/)
./.venv/Scripts/python.exe src/train/train_ppo.py --smoke --timesteps 256 --n-envs 1 --dummy-vec --no-bc

# отладка без smoke: явный tmp/ или --no-intermediate-checkpoints
./.venv/Scripts/python.exe src/train/train_ppo.py --timesteps 256 --n-envs 1 --dummy-vec --no-intermediate-checkpoints
```

| Аргумент | Описание |
| -------- | -------- |
| `--task` | `tasks/train_task.json` (finetune: checkpoint_in/out, hot_zone, seg) |
| `--timesteps` | total PPO steps (default 500000) |
| `--n-envs` | parallel FCEUX (default 8) |
| `--save-every` | checkpoint каждые N steps (default 50000) |
| `--checkpoint-in` / `--checkpoint-out` | load/save `.zip` |
| `--resume` / `--no-resume` | продолжить с `checkpoint_out` + sidecar `.train.json` (default: resume on) |
| `--latest-checkpoint` | дополнительно `checkpoints/latest.zip` на каждый rollout PPO |
| `--bc-epochs` | BC epochs перед PPO (0 = skip; нужны demos без obs_stub) |
| `--dummy-vec` | DummyVecEnv вместо SubprocVecEnv |
| `--smoke` | checkpoint в `tmp/smoke/<session>/`; `finally` удаляет сессию; без `runs/` и resume |
| `--smoke-session` | имя подкаталога `tmp/smoke/` (default `train_smoke`) |
| `--no-intermediate-checkpoints` | без `CheckpointCallback` / `checkpoints/runs/` |
| `--progress` | tqdm/rich progress bar (отключает текстовый `train: N%`) |
| `--no-progress-pct` | не печатать `train: 42.3% (211500/500000 steps)` в stderr |

**Smoke train:** для короткой проверки PPO — `--smoke`, не `--checkpoint-out checkpoints/smoke_*.zip` в миссии. Для bridge/env — `run_smoke.py`, не `train_ppo`.

По умолчанию в stderr каждые ~5 с (и в начале/конце) — строка **`train: 42.3% (211500/500000 steps)`** от полного `target_timesteps` (в т.ч. при resume). SB3 `verbose=1` и `--save-every` не меняются.

**Прерывание и resume:** Ctrl+C или SIGTERM сохраняют `checkpoint_out` атомарно (`*.tmp.zip` → rename) и обновляют sidecar `*.train.json` (`target_timesteps`, `game`, `mission`, `n_envs`, `save_state`). Повторный запуск с тем же `--checkpoint-out` продолжает до `target_timesteps` (`PPO.load`, `reset_num_timesteps=False`). BC при resume не повторяется. Несовпадение `--n-envs` с sidecar → отказ. Явный finetune: `--checkpoint-in other.zip --checkpoint-out new.zip --no-resume`.

При `Bridge ready timeout` или `FCEUX exited before ready` — зависшие процессы от прошлого train. `train_ppo.py` при старте завершает headless FCEUX с `bridge.lua`; вручную: `taskkill /F /IM fceux64.exe`.

### Inference

```bash
# базовый прогон
./.venv/Scripts/python.exe src/stream/run_inference.py --checkpoint m1_v0.zip --episodes 10

# с окном FCEUX, FM2 и плейлистом achievements
./.venv/Scripts/python.exe src/stream/run_inference.py \
  --checkpoint m1_v0.zip --episodes 5 \
  --save-episode-fm2 --build-playlist
```

Логи (плоский `games/…/missions/m1/logs/`, префикс UTC-даты, retention 4 ч):

- `YYYYMMDD_attempts.jsonl` — одна строка на эпизод (`tags[]`, death, reward, …)
- `YYYYMMDD_inference_inputs.jsonl` — покадровый `(frame, action)` для FM2

| Аргумент | Описание |
| -------- | -------- |
| `--checkpoint` | `checkpoints/m1_v0.zip` или имя файла |
| `--game` / `--mission` | игра и миссия (default `rushn_attack` / `m1`) |
| `--episodes` | число эпизодов (default 5) |
| `--max-steps` | лимит env steps на эпизод (default 8000) |
| `--save-state` | save state на reset (default `states/inference_cp0.fc0` — gameplay start) |
| `--reward-profile` | профиль наград из `routes.yaml` (default `default`) |
| `--model-version` | метка в логе (default — stem checkpoint) |
| `--session` | id сессии FCEUX bridge (default `inference`) |
| `--stochastic` | sampling вместо argmax |
| `--fceux-profile` | профиль `fceux/profiles/{name}.yaml` (default `inference` → окно FCEUX) |
| `--show-window` | явно показать окно FCEUX (иначе из профиля) |
| `--turbo` | override turbo из профиля |
| `--export-fm2 PATH` | экспорт FM2 последнего эпизода (для одного ep: `--episodes 1`) |
| `--export-fm2-dir DIR` | FM2 по эпизодам в каталог |
| `--save-episode-fm2` | `logs/YYYYMMDD_epNNNN.fm2` на каждый эпизод (embedded savestate) |
| `--build-playlist` | после прогона — FM2-плейлист по номинациям |

После эпизода overlay пишется в `tmp/bridge/inference/overlay.json` (рисуется в `bridge.lua`).

### FM2 из inference (без reference/)

**Self-contained FM2:** inference-клип можно открыть в FCEUX как **ROM + один `.fm2`** — Load ROM → Play Movie, без отдельного `-loadstate`. Save state вшит в заголовок (`savestate 0x…`) с inference GUID (`fm2_export.INFERENCE_FM2_GUID`); GUID эталона `clear.fm2` в `.fc0` патчится при экспорте.

```bash
# из jsonl (всегда embedded)
./.venv/Scripts/python.exe scripts/export_fm2.py \
  -o logs/20260705_m1_v0_ep42.fm2 --episode 42

# через inference
./.venv/Scripts/python.exe src/stream/run_inference.py \
  --checkpoint m1_v0.zip --episodes 1 --save-episode-fm2
```

| Аргумент | Описание |
| -------- | -------- |
| `--input` | `logs/YYYYMMDD_inference_inputs.jsonl` (default — за сегодня UTC) |
| `-o` / `--output` | путь к `.fm2` (обязательный) |
| `--episode` | только один эпизод из jsonl |
| `--frame-skip` | NES-кадров на env step (default 4) |
| `--template` | заголовок FM2 (default `fceux/portable/movies/`) |
| `--save-state` | путь к `.fc0` для embed (default `states/inference_cp0.fc0`) |

**Отличие от эталона:** `reference/clear.fm2` — полное прохождение с power-on и GUID эталона; inference FM2 — короткий клип с gameplay-start state, отдельный GUID, без `length` в заголовке (не FM3).

**Sidecar:** `.overlay.json` — только achievement-overlay (Lua); без `save_state`.

Reset inference в env/train — `states/inference_cp0.fc0` (gameplay start, кадр из `playthrough_manifest.yaml` → `inference.gameplay_start_frame`); train env по-прежнему использует `states/cp0.fc0` из manifest сегментов.

### Replay FM2 / плейлист эфира

```bash
# один клип (отладка)
./.venv/Scripts/python.exe scripts/play_inference_fm2.py \
  games/rushn_attack/missions/m1/logs/20260705_ep0001.fm2

# эфир: весь плейлист подряд
./.venv/Scripts/python.exe scripts/play_inference_fm2.py \
  games/rushn_attack/missions/m1/logs/20260705_playlist.json
```

| Аргумент | Описание |
| -------- | -------- |
| `input` | путь к self-contained `.fm2` или `YYYYMMDD_playlist.json` |
| `--overlay` | default: `{fm2}.overlay.json` (single FM2) |
| `--turbo` | макс. скорость |

Эфирный лаунчер: `logs/YYYYMMDD_playlist.play.cmd` (генерируется `build_playlist`).

Replay требует **embedded** FM2 (savestate в заголовке). Lua: `achievement_overlay.lua`; Python передаёт `WAIT_ACHIEVEMENT_OVERLAY` и `WAIT_BLOCK_LABEL` (плейлист). Без `-loadstate` и без внешнего `.fc0`.

### Achievements и плейлист

Правила: [`config/achievements.yaml`](../config/achievements.yaml).

```bash
# пересчитать tags[] в attempts
./.venv/Scripts/python.exe scripts/eval_achievements.py

# собрать FM2 + playlist.json по номинациям
./.venv/Scripts/python.exe scripts/build_playlist.py
```

| Скрипт | Аргумент | Описание |
| ------ | -------- | -------- |
| `eval_achievements.py` | `--attempts` | путь к attempts (default `logs/YYYYMMDD_attempts.jsonl`) |
| | `--config` | путь к `achievements.yaml` |
| `build_playlist.py` | `--attempts` | то же |
| | `--inputs` | `inference_inputs.jsonl` для on-demand FM2 |

Выход плейлиста: `logs/YYYYMMDD_{idx:02d}_{slug}_{seq:03d}.fm2` + sidecar `.overlay.json`, manifest `logs/YYYYMMDD_playlist.json`, лаунчер `logs/YYYYMMDD_playlist.play.cmd`.

**Состав клипа плейлиста:**

| Артефакт | Назначение |
| -------- | ---------- |
| `.fm2` | inputs + embedded `savestate` (gameplay start) |
| `.overlay.json` | achievements для Lua (`achievements`, `stats`, `show_until_frame`) |
| `YYYYMMDD_playlist.json` | порядок эфира (`idx`, `slug`, `block_label`, `fm2`, `overlay`) |
| `.play.cmd` | один запуск `play_inference_fm2.py` с manifest |

ROM общий для всего плейлиста (staging в `play_inference_fm2.py`). On-demand экспорт в `build_playlist` (`--inputs`) — с `--embed-savestate` (из 3.1).

---

## Запланировано (ещё не в репо)

| Скрипт | Фаза | Назначение |
| ------ | ---- | ---------- |
| `build_train_task.py` | 3 | failure → `tasks/train_task.json` |

---

## См. также

- [ML_CONCEPT.md §10](ML_CONCEPT.md#10-структура-репозитория) — структура каталогов
- [ML_CONCEPT.md §10 «В проекте vs окружение»](ML_CONCEPT.md#в-проекте-vs-окружение) — git / venv / portable
