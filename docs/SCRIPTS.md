# SCRIPTS — каталог консольных entry point'ов

> Запуск из корня репозитория.  
> Python: `.venv\Scripts\python.exe` (или активированный `.venv`).

**Область документа:** только скрипты и CLI entry point'ы (`scripts/*`, `src/train/train_ppo.py`, `src/stream/run_inference.py`) — назначение, типовая команда, вход/выход, флаги.

**Не писать сюда:** замеры FPS/ms, таблицы baseline, backlog-номера этапов, runbook расследований, описания контрактов данных, pytest-сюиты.  
→ метрики: [MEASUREMENTS.md](MEASUREMENTS.md) · контракты: [ML_CONCEPT.md §8](ML_CONCEPT.md#8-форматы-данных) · задачи: [TASK_BLANK](tasks/TASK_BLANK.md) · гигиена: [DESIGN.md](DESIGN.md#гигиена-артефактов).

**Синхронизация:** алгоритм add/change/remove — [DESIGN § Регистрация скриптов](DESIGN.md#регистрация-скриптов-в-scriptsmd). Здесь — только каталог; устаревшие флаги не оставлять.

---

## Карта задач

| Хочу… | Скрипт |
| ----- | ------ |
| Поставить `.venv` | [`setup_all.ps1`](#setup_allps1) → [`verify_env.py`](#verify_envpy) |
| RAM-разведка эталона | [`ram_scout.py`](#ram_scoutpy) |
| Собрать эталон (jsonl, save_states, demos_for_bc stub) | [`build_playthrough.py`](#build_playthroughpy) |
| Только inference save state | [`build_inference_states.py`](#build_inference_statespy) |
| Demos с реальными obs (BC) | [`record_demos.py`](#record_demospy) |
| Smoke после правок bridge/env | [`run_smoke.py`](#run_smokepy) |
| Обучение PPO | [`train_local.sh`](#train_localsh) → [`train_ppo.py`](#train_ppopy) |
| Inference + плейлист | [`inference_local.sh`](#inference_localsh) → [`run_inference.py`](#run_inferencepy) |
| Replay клипа / эфир | [`play_inference_fm2.py`](#play_inference_fm2py) |
| Benchmark bridge / e2e train | [`benchmark_bridge.py`](#benchmark_bridgepy), [`benchmark_train.py`](#benchmark_trainpy) |
| Разбор `rollouts.jsonl` | [`parse_train_rollouts.py`](#parse_train_rolloutspy) |

---

## Индекс

| Скрипт | Назначение |
| ------ | ---------- |
| [`bench_parallel_step.py`](#bench_parallel_steppy) | Быстрый замер latency parallel step (4 env, без CLI) |
| [`benchmark_bridge.py`](#benchmark_bridgepy) | Benchmark IPC bridge → `tmp/bench/` |
| [`benchmark_train.py`](#benchmark_trainpy) | E2E PPO benchmark → `tmp/bench/` |
| [`build_inference_states.py`](#build_inference_statespy) | `save_states/inference_cp0.fc0` + блок `inference` в manifest |
| [`build_playlist.py`](#build_playlistpy) | FM2-плейлист по номинациям |
| [`build_playthrough.py`](#build_playthroughpy) | Эталон: jsonl, routes, save_states, demos_for_bc |
| [`eval_achievements.py`](#eval_achievementspy) | `tags[]` в `attempts.jsonl` |
| [`export_fm2.py`](#export_fm2py) | `inference_inputs.jsonl` → self-contained `.fm2` |
| [`inference_local.sh`](#inference_localsh) | Фасад: preflight → `run_inference` |
| [`inference_preflight.py`](#inference_preflightpy) | Очистка перед inference / playback |
| [`parse_train_rollouts.py`](#parse_train_rolloutspy) | Сводка `rollouts.jsonl` |
| [`play_fm2_gui.py`](#play_fm2_guipy) | GUI replay одного FM2 (отладка) |
| [`play_inference_fm2.py`](#play_inference_fm2py) | Replay FM2 или `playlist.json` |
| [`ram_scout.py`](#ram_scoutpy) | RAM scout эталонного FM2 |
| [`record_demos.py`](#record_demospy) | Demos с реальными obs |
| [`run_smoke.py`](#run_smokepy) | Единый smoke entry point |
| [`segment_playthrough.py`](#segment_playthroughpy) | Demos actions-only (obs=stub) |
| [`setup_all.ps1`](#setup_allps1) | Setup: venv (+ FCEUX вручную) |
| [`setup_venv.ps1`](#setup_venvps1) | Создать `.venv`, `requirements.txt` |
| [`smoke_bridge.py`](#smoke_bridgepy) | Smoke IPC bridge |
| [`smoke_env.py`](#smoke_envpy) | Smoke Gymnasium env |
| [`stress_e2e_gate.py`](#stress_e2e_gatepy) | Длительный IPC/gate stress |
| [`stress_parallel_reset.py`](#stress_parallel_resetpy) | Короткий parallel reset stress (устаревший относительно gate) |
| [`test_parallel_env.py`](#test_parallel_envpy) | Parallel vec step + reset |
| [`train_fps_round_prep.py`](#train_fps_round_preppy) | Prep `models/gen0` для fps-раунда |
| [`train_local.sh`](#train_localsh) | Фасад: preflight → `train_ppo` (`--n-envs 6`) |
| [`train_preflight.py`](#train_preflightpy) | Очистка перед train |
| [`verify_env.py`](#verify_envpy) | Проверка импортов ML-стека |
| [`src/stream/run_inference.py`](#run_inferencepy) | Локальный inference |
| [`src/train/train_ppo.py`](#train_ppopy) | PPO train |

Модуль без CLI: `src/train/bc_pretrain.py` (вызывается из `train_ppo` при `--bc-epochs`).

---

## Карточки

Шаблон: **назначение** → команда → вход/выход → флаги (частые сверху).  
Общие `--game` / `--mission` (default `rushn_attack` / `m1`) у многих скриптов ниже не дублируются, если нет особого смысла.

---

### `setup_venv.ps1`

Создаёт `.venv`, ставит `requirements.txt`.

```powershell
.\scripts\setup_venv.ps1
```

---

### `setup_all.ps1`

Вызывает `setup_venv` (FCEUX — вручную в `fceux/portable/`).

```powershell
.\scripts\setup_all.ps1
```

---

### `verify_env.py`

Проверка импортов ML-стека. CLI нет.

```bash
./.venv/Scripts/python.exe scripts/verify_env.py
```

---

### `ram_scout.py`

FM2 → `reference/scout/ram_scout.jsonl`, `config/ram_resolve.json`, `ram_map.md`.

```bash
./.venv/Scripts/python.exe scripts/ram_scout.py games/rushn_attack/missions/m1/reference/clear.fm2
```

| Флаг | Описание |
| ---- | -------- |
| `fm2` | путь к FM2 |
| `--timeout` | лимит секунд FCEUX (default 600) |
| `--no-ram-map` | не обновлять `ram_map.md` |

---

### `build_playthrough.py`

После `ram_scout`: `human_playthrough.jsonl`, `config/routes.yaml`, `playthrough_manifest.yaml`, train `save_states/cp*.fc0`, `reference/demos_for_bc` (stub obs), опц. inference state.

`cp0.fc0` — reset train; `inference_cp0.fc0` — старт gameplay для inference/плейлиста.

```bash
./.venv/Scripts/python.exe scripts/build_playthrough.py games/rushn_attack/missions/m1/reference/clear.fm2
```

| Флаг | Описание |
| ---- | -------- |
| `fm2` | путь к FM2 |
| `--timeout` | лимит FCEUX (default 600) |
| `--skip-states` | без train `cp*.fc0` |
| `--skip-inference-states` | без `inference_cp0.fc0` |
| `--skip-demos` | без `reference/demos_for_bc/seg_*.npz` |

---

### `build_inference_states.py`

Только `save_states/inference_cp0.fc0` + блок `inference` в manifest.

```bash
./.venv/Scripts/python.exe scripts/build_inference_states.py games/rushn_attack/missions/m1/reference/clear.fm2
```

| Флаг | Описание |
| ---- | -------- |
| `fm2` | путь к FM2 |
| `--timeout` | лимит FCEUX (default 600) |

---

### `segment_playthrough.py`

`reference/demos_for_bc/seg_*.npz` с actions only (`obs` stub). Для BC с кадрами — `record_demos.py`.

```bash
./.venv/Scripts/python.exe scripts/segment_playthrough.py games/rushn_attack/missions/m1/reference/clear.fm2
```

| Флаг | Описание |
| ---- | -------- |
| `fm2` | путь к FM2 (миссия) |

---

### `record_demos.py`

Demos с реальными obs `(N, 4, 84, 84)` для `--bc-epochs`. Параллельно по умолчанию (`min(segments, cpu, 8)`).

```bash
./.venv/Scripts/python.exe scripts/record_demos.py games/rushn_attack/missions/m1/reference/clear.fm2
./.venv/Scripts/python.exe scripts/record_demos.py games/rushn_attack/missions/m1/reference/clear.fm2 --segment seg_001 --max-steps 20 --jobs 1
```

| Флаг | Описание |
| ---- | -------- |
| `fm2` | путь к FM2 |
| `--segment ID` | только указанные сегменты (можно несколько раз) |
| `--max-steps` | лимит env steps (отладка) |
| `--jobs` | parallel FCEUX (`1` = последовательно) |
| `--session` | id bridge (default `record_demos`) |
| `--no-turbo` | без turbo |

---

### `run_smoke.py`

Единый smoke после правок bridge/env. Subprocess: `smoke_bridge`, `smoke_env --steps 20`, `test_parallel_env`, опц. `stress_e2e_gate --quick`. Exit 0/1; cleanup quarantine в `finally`.

```bash
./.venv/Scripts/python.exe scripts/run_smoke.py
./.venv/Scripts/python.exe scripts/run_smoke.py --suite bridge,env,parallel
./.venv/Scripts/python.exe scripts/run_smoke.py --suite stress
```

| Флаг | Описание |
| ---- | -------- |
| `--suite` | `bridge`, `env`, `parallel`, `stress` (default — первые три) |

Pytest-аналог: `pytest tests/smoke/` (не часть этого каталога).

---

### `smoke_bridge.py`

Smoke IPC `FceuxBridge` (нужен `save_states/cp1.fc0`). CLI нет.

```bash
./.venv/Scripts/python.exe scripts/smoke_bridge.py
```

---

### `smoke_env.py`

Random agent / короткий env smoke. `--log` пишет в `games/.../logs/` — только при необходимости.

```bash
./.venv/Scripts/python.exe scripts/smoke_env.py --steps 100
```

| Флаг | Описание |
| ---- | -------- |
| `--steps` | число шагов (default 100) |
| `--save-state` | относительно миссии (default `save_states/cp1.fc0`) |
| `--session` | id bridge (default `smoke_env`) |
| `--death-mode` | `life_lost` \| `game_over` (override `env_config.yaml`; H3) |
| `--log` | append в `logs/YYYYMMDD/attempts.jsonl` |
| `--game` / `--mission` | игра / миссия |

---

### `test_parallel_env.py`

`SubprocVecEnv`: step + периодический reset (без PPO).

```bash
./.venv/Scripts/python.exe scripts/test_parallel_env.py --n-envs 8 --cycles 30 --reset-every 5
```

| Флаг | Описание |
| ---- | -------- |
| `--n-envs` | parallel env (default 8) |
| `--cycles` | раундов step (default 30) |
| `--reset-every` | `vec.reset()` каждые N циклов (default 5; `0` = только initial) |
| `--save-state` | default `save_states/cp0.fc0` |
| `--game` / `--mission` | |

---

### `stress_e2e_gate.py`

Пять фаз gate-shaped stress (без полного `benchmark_train`). Детали расследования — [ISSUE_FALL.md](tasks/archive/ISSUE_FALL.md).

```bash
./.venv/Scripts/python.exe scripts/stress_e2e_gate.py --quick
./.venv/Scripts/python.exe scripts/stress_e2e_gate.py --full
./.venv/Scripts/python.exe scripts/stress_e2e_gate.py --phase vec_rollout_2 --full
```

| Флаг | Описание |
| ---- | -------- |
| `--quick` / `--full` | глубина rollout (default quick) |
| `--phase` | `bridge_parallel`, `vec_rollout_1`, `ppo_spike`, `ppo_spike_with_vec`, `vec_rollout_2` |
| `--n-envs` | default 8 |
| `--cycles` | vec steps (override quick/full) |
| `--bridge-steps` | STEP-only на env в `bridge_parallel` |
| `--batch-size`, `--n-epochs`, `--threads` | фаза `ppo_spike` |
| `--fail-fast` / `--no-fail-fast` | (default fail-fast on) |
| `--json-out` | default `tmp/smoke/stress_e2e/report.json` |
| `--save-state`, `--frame-skip`, `--game`, `--mission` | |

---

### `stress_parallel_reset.py`

Короткий stress: 4 env, ~90 s auto-reset. Ужее, чем `stress_e2e_gate`. CLI нет.

```bash
./.venv/Scripts/python.exe scripts/stress_parallel_reset.py
```

---

### `benchmark_bridge.py`

IPC throughput → JSON в `tmp/bench/` (не `games/.../models/`). Числа baseline — [MEASUREMENTS.md](MEASUREMENTS.md).

```bash
./.venv/Scripts/python.exe scripts/benchmark_bridge.py --n-envs 8
```

| Флаг | Описание |
| ---- | -------- |
| `--n-envs` | parallel FCEUX (default 8) |
| `--step-samples` / `--reset-samples` | число замеров (30 / 10) |
| `--parallel-steps` | steps на env в parallel-фазе (default 20) |
| `--step-warmup` | default 5 |
| `--ep-len2-cycles` / `--ep-len2-steps` | профиль ep_len≈2 (64 / 2; `0` cycles = skip) |
| `--gate-vec-cycles` | проекция gate rollout (default 128) |
| `--json-out` | путь отчёта |
| `--session` | id bridge (default `bench_bridge`) |
| `--save-state`, `--frame-skip`, `--game`, `--mission` | |

---

### `benchmark_train.py`

E2E PPO `learn` → `tmp/bench/<session>/`. Перед learn — preflight orphan IPC.

```bash
./.venv/Scripts/python.exe scripts/benchmark_train.py --dry-run
./.venv/Scripts/python.exe scripts/benchmark_train.py --mode gate
./.venv/Scripts/python.exe scripts/benchmark_train.py --mode fps
```

| Флаг | Описание |
| ---- | -------- |
| `--mode` | `gate` (2048) / `fps` (8192) / `custom` |
| `--timesteps` | override режима |
| `--n-envs` | default 8 |
| `--warmup-rollouts` | вне steady fps (default 1) |
| `--session` | `tmp/bench/<session>/` (default `train_e2e`) |
| `--bridge-report` | JSON `benchmark_bridge` для сравнения |
| `--json-out` | путь `train_report.json` |
| `--dry-run` | только пути |
| `--dummy-vec` / `--quiet` | отладка |
| `--learn-stall-timeout` | abort без прогресса timesteps, с (default 300; `0`=off) |
| `--session-wall-timeout` | abort по wall сессии, с (default 3600; `0`=off) |
| `--n-steps`, `--batch-size`, `--n-epochs`, `--gamma`, `--learning-rate`, `--threads` | PPO |
| `--save-state`, `--game`, `--mission` | |

---

### `bench_parallel_step.py`

Фиксированный замер: 4 env, 50 steps, stdout latency. CLI нет.

```bash
./.venv/Scripts/python.exe scripts/bench_parallel_step.py
```

---

### `train_preflight.py`

Очистка `train_`/`bench_` IPC + orphan FCEUX/python. Exit 1, если после cleanup остались процессы. CLI нет. Вызывается из `train_local.sh`.

```bash
./.venv/Scripts/python.exe scripts/train_preflight.py
```

---

### `train_local.sh`

Фасад: `train_preflight` → `train_ppo` с **`--n-envs 6`** (если не передан task JSON). Остальные аргументы — как у `train_ppo`.

```bash
./scripts/train_local.sh --timesteps 50000 --save-every 10000 --model-out models/gen0.zip
./scripts/train_local.sh path/to/train_task.json
```

---

### `train_ppo.py`

<a id="train_ppopy"></a>

PPO на CPU / FCEUX env. Поколения модели: `games/.../models/genN.zip` (или `tmp/smoke/` при `--smoke`).  
Модуль BC: `src/train/bc_pretrain.py` (при `--bc-epochs > 0`, demos без `obs_stub`).

```bash
./scripts/train_local.sh --timesteps 50000 --model-out models/gen0.zip
./.venv/Scripts/python.exe src/train/train_ppo.py --smoke --timesteps 256 --n-envs 1 --dummy-vec --no-bc
```

| Флаг | Описание |
| ---- | -------- |
| `--task` | `tasks/train_task.json` |
| `--timesteps` | total steps (default 500000) |
| `--n-envs` | parallel FCEUX (default **8**; через `train_local.sh` → **6**) |
| `--model-in` / `--model-out` | load/save `.zip` (default out: `models/gen0.zip`) |
| `--resume` / `--no-resume` | sidecar `.train.json` (default on) |
| `--latest-model` / `--no-latest-model` | `models/latest.zip` (default on) |
| `--latest-every` | latest.zip каждые N rollout (default **5**, H5; `1` = каждый) |
| `--recycle-every-timesteps` | H4: пересоздать FCEUX/vec каждые N steps (`0`=off) |
| `--session-wall-timeout` | H6: abort по wall-clock сессии, с (`0`=off); resume из model zip |
| `--save-every` | каждые N steps (default 50000) |
| `--bc-epochs` / `--bc-demo` / `--no-bc` | BC warm-start |
| `--rollout-gc` / `--no-rollout-gc` | `gc.collect` после rollout (default on) |
| `--rollout-metrics` / `--no-rollout-metrics` | JSONL в `tmp/bench/` (default off) |
| `--rollout-metrics-session` / `--rollout-metrics-path` | куда писать metrics |
| `--smoke` / `--smoke-session` | карантин `tmp/smoke/` |
| `--no-intermediate-models` | без `models/runs/` |
| `--dummy-vec` | DummyVecEnv |
| `--no-turbo` | отладка |
| `--progress` / `--no-progress-pct` | UX таблицы SB3 |
| `--learn-stall-timeout` | abort без прогресса timesteps (default 300; `0`=off) |
| `--skip-preflight` | не вызывать preflight (только прямой вызов) |
| `--n-steps`, `--batch-size`, `--n-epochs`, `--gamma`, `--learning-rate`, `--threads` | PPO гиперпараметры |
| `--save-state`, `--reward-profile`, `--game`, `--mission` | |
| `--death-mode` | `life_lost` \| `game_over` (default из `env_config.yaml`; H3) |

Resume: Ctrl+C/SIGTERM → атомарный save + sidecar; повтор с тем же `--model-out` продолжает до `target_timesteps`. CLI `--timesteps` больше sidecar → цель поднимается.

---

### `train_fps_round_prep.py`

Архив `models/gen0.zip` + печать команд для fps/dual-train раунда. Runbook — [TASK_TRAIN_FPS_DEGRADATION](tasks/archive/TASK_TRAIN_FPS_DEGRADATION.md).

```bash
./.venv/Scripts/python.exe scripts/train_fps_round_prep.py
```

| Флаг | Описание |
| ---- | -------- |
| `--force-promote` | перезаписать target даже если уже есть |
| `--target-timesteps` | цель для длинного прогона |
| `--session` | метка metrics-сессии |
| `--game` / `--mission` | |

---

### `parse_train_rollouts.py`

Сводка wall_rollout / degradation из `rollouts.jsonl`.

```bash
./.venv/Scripts/python.exe scripts/parse_train_rollouts.py --jsonl tmp/bench/train_fps/rollouts.jsonl
```

| Флаг | Описание |
| ---- | -------- |
| `--jsonl` | путь к `rollouts.jsonl` (обязательный) |
| `--json` | только JSON в stdout |

---

### `inference_preflight.py`

Перед inference: staging/bridge; **logs дня по умолчанию сохраняются** (печатает текущий airtime). Wipe — только по флагу. Вызывается из `inference_local.sh` / `play_inference_fm2`.

```bash
./.venv/Scripts/python.exe scripts/inference_preflight.py
./.venv/Scripts/python.exe scripts/inference_preflight.py --wipe-day-logs
./.venv/Scripts/python.exe scripts/inference_preflight.py --playback-only
```

| Флаг | Описание |
| ---- | -------- |
| `--playback-only` | только staging/bridge (для replay, без wipe logs) |
| `--wipe-day-logs` | удалить `logs/YYYYMMDD/` текущего retention-дня перед сбором |
| `--game` / `--mission` | |

---

### `inference_local.sh`

Фасад: preflight → `run_inference`. Без аргументов — короткий прогон (`--episodes 5`, playlist). Свои флаги оболочки: `--play`, `--skip-preflight`, `--wipe-day-logs`; остальное — в `run_inference`.

```bash
# Короткий прогон (без target-airtime)
./scripts/inference_local.sh
./scripts/inference_local.sh --model gen0.zip --episodes 3 --play

# Эфир ~1 ч realtime (дефолт при флаге без значения)
./scripts/inference_local.sh --stochastic --target-airtime --episodes 5

# Smoke-target 2–3 мин → playlist airtime ≥ target → опц. replay
# Автотест: pytest tests/test_playlist_airtime_smoke.py -m slow
./scripts/inference_local.sh --stochastic --target-airtime 2m --episodes 8 --max-steps 80 --play

# С нуля за день (wipe) + тот же smoke
./scripts/inference_local.sh --wipe-day-logs --stochastic --target-airtime 3m --episodes 5
```

| Флаг оболочки | Описание |
| ------------- | -------- |
| `--play` | после прогона вызвать `play_inference_fm2` на playlist |
| `--skip-preflight` | не вызывать `inference_preflight` |
| `--wipe-day-logs` | снести накопление дня перед сбором (default: keep) |

---

### `run_inference.py`

<a id="inference"></a>
<a id="run_inferencepy"></a>

Локальный PPO inference. Логи: `games/.../logs/YYYYMMDD/` (`attempts.jsonl`, `inference_inputs.jsonl`). Default save state: `save_states/inference_cp0.fc0`.  
[Retention window](GLOSSARY.md#retention-window) — пул attempts за календарный день (UTC+3); не путать с [airtime](GLOSSARY.md#airtime) плейлиста (длина эфира, дефолт 1 ч). Подробнее — ML_CONCEPT §8.

```bash
# Фиксированное число эпизодов + плейлист
./.venv/Scripts/python.exe src/stream/run_inference.py \
  --model gen0.zip --episodes 5 --stochastic --build-playlist

# Сбор под эфир N часов (стоп по airtime, pad; --episodes = размер батча)
./.venv/Scripts/python.exe src/stream/run_inference.py \
  --model gen0.zip --stochastic --target-airtime 1h --episodes 5

# Smoke-target ~2 мин (короткие эпизоды → pad/hold набирают airtime)
./.venv/Scripts/python.exe -u src/stream/run_inference.py \
  --model gen0.zip --stochastic --target-airtime 2m --episodes 8 --max-steps 80
```

| Флаг | Описание |
| ---- | -------- |
| `--model` | `.zip` или имя в `models/` (default `gen0.zip`) |
| `--episodes` / `--max-steps` | default 5 / 8000; при `--target-airtime` — размер батча добора |
| `--stochastic` | sampling (рекомендуется vs greedy) |
| `--save-state` | reset state (default `inference_cp0.fc0`) |
| `--save-episode-fm2` | писать FM2 эпизодов |
| `--build-playlist` | плейлист по номинациям |
| `--playlist-no-dedupe` | без дедупа эпизодов в плейлисте |
| `--show-window` | видимое окно (default headless) |
| `--fceux-profile` | default `inference` |
| `--turbo` | force turbo on |
| `--session` | id bridge (default `inference`) |
| `--reward-profile` / `--model-version` | |
| `--target-airtime` | целевой airtime (`1h` / `3m` / `120s`; флаг без значения = 1h); цикл + pad |
| `--max-airtime-batches` | лимит батчей добора (default 200) |
| `--wipe-day-logs` | wipe `logs/YYYYMMDD/` перед сбором (default: keep + учесть airtime) |
| `--skip-preflight` | |
| `--game` / `--mission` | |

---

### `export_fm2.py`

<a id="fm2-из-inference-без-reference"></a>

`inference_inputs.jsonl` → self-contained `.fm2` (embed savestate всегда). Не для BC — только просмотр / эфир.

```bash
./.venv/Scripts/python.exe scripts/export_fm2.py -o logs/clip.fm2 --episode 42
```

| Флаг | Описание |
| ---- | -------- |
| `-o` / `--output` | путь `.fm2` (обязательный) |
| `--input` | jsonl (default — сегодня, день retention window) |
| `--episode` | один эпизод |
| `--frame-skip` | NES-кадров на env step (default 4) |
| `--template` | заголовок FM2 |
| `--save-state` | `.fc0` для embed (default `inference_cp0.fc0`) |
| `--game` / `--mission` | |

---

### `eval_achievements.py`

Правила [`config/achievements.yaml`](../config/achievements.yaml) → `tags[]` в attempts. Номинации пилота — [GAME_RUSHN_ATTACK.md §5](GAME_RUSHN_ATTACK.md#5-achievements-номинации-пилота).

```bash
./.venv/Scripts/python.exe scripts/eval_achievements.py
```

| Флаг | Описание |
| ---- | -------- |
| `--attempts` | путь к attempts (default — сегодня, день retention window) |
| `--config` | путь к YAML |
| `--game` / `--mission` | |

---

### `build_playlist.py`

<a id="achievements-и-плейлист"></a>

Attempts (+ опц. inputs) → `NN_slug_MMM.fm2`, `.overlay.json`, `playlist.json` (поле `airtime`), `playlist.play.cmd`.  
Кандидаты — из [retention window](GLOSSARY.md#retention-window); целевая длина replay — [airtime](GLOSSARY.md#airtime). Обычный сбор под N часов — через `run_inference --target-airtime` (см. выше); этот скрипт — пересборка / pad из уже накопленного дня.

```bash
./.venv/Scripts/python.exe scripts/build_playlist.py
./.venv/Scripts/python.exe scripts/build_playlist.py --inputs logs/YYYYMMDD/inference_inputs.jsonl

# Добить pad-клипами до N (часы / минуты), не меняя порядок номинаций
./.venv/Scripts/python.exe scripts/build_playlist.py --pad-to-airtime 1h
./.venv/Scripts/python.exe scripts/build_playlist.py --pad-to-airtime 3m
```

| Флаг | Описание |
| ---- | -------- |
| `--attempts` | attempts.jsonl |
| `--inputs` | on-demand FM2 из inputs |
| `--no-dedupe` | не пропускать дубликаты эпизодов |
| `--pad-to-airtime` | pad до N (`1h`, `3m`, …) после блоков номинаций |
| `--game` / `--mission` | |

Выход в `logs/YYYYMMDD/`: `.fm2` (embed savestate), `.overlay.json`, `playlist.json` (+ `airtime`), `.play.cmd`.

---

### `play_inference_fm2.py`

Replay одного self-contained `.fm2` или всего `playlist.json` (эфир).

```bash
# После smoke-сбора (YYYYMMDD = день retention UTC+3)
./.venv/Scripts/python.exe scripts/play_inference_fm2.py \
  games/rushn_attack/missions/m1/logs/YYYYMMDD/playlist.json
./.venv/Scripts/python.exe scripts/play_inference_fm2.py path/to/clip.fm2
```

| Флаг | Описание |
| ---- | -------- |
| `input` | `.fm2` или `playlist.json` |
| `--overlay` | sidecar (default `{fm2}.overlay.json`) |
| `--turbo` | макс. скорость |
| `--noicon` | скрыть окно |
| `--timeout` | default 120 |
| `--skip-preflight` | |
| `--game` / `--mission` | |

---

### `play_fm2_gui.py`

GUI replay одного FM2 (отладка embed / movie).

```bash
./.venv/Scripts/python.exe scripts/play_fm2_gui.py path/to/clip.fm2
```

| Флаг | Описание |
| ---- | -------- |
| `fm2` | путь к `.fm2` |
| `--no-refresh-embed` | не обновлять embedded savestate |
| `--turbo` | |
| `--timeout` | |
| `--game` / `--mission` | |

---

## См. также

- [MEASUREMENTS.md](MEASUREMENTS.md) — baseline FPS / ms
- [DESIGN.md § Структура репозитория](DESIGN.md#структура-репозитория) · [гигиена](DESIGN.md#гигиена-артефактов)
- [ML_CONCEPT.md §8](ML_CONCEPT.md#8-форматы-данных) — контракты данных
