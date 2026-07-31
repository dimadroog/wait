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
| RAM-разведка (shell / mission) | [`ram_scout.py`](#ram_scoutpy) |
| Скомпилировать RAM-триггеры CP (`route_triggers.yaml`) | [`compile_route_triggers.py`](#compile_route_triggerspy) |
| Собрать эталон (jsonl, save_states) | [`build_playthrough.py`](#build_playthroughpy) |
| Пересобрать save states из `head_save_states` | [`build_playthrough.py --states-only`](#build_playthroughpy) |
| Demos с реальными obs (BC) | [`record_demos.py`](#record_demospy) |
| PNG-превью BC-демо | [`preview_demos.py`](#preview_demospy) |
| Smoke после правок bridge/env | [`run_smoke.py`](#run_smokepy) |
| Обучение PPO | [`train_local.sh`](#train_localsh) → [`train_ppo.py`](#train_ppopy) |
| Inference pool (N + playlist) или live (до Ctrl+C) | [`inference_local.sh`](#inference_localsh) → [`run_inference.py`](#run_inferencepy) |
| Короткий editorial + board | [`hybrid_episode_prep.py`](#hybrid_episode_preppy) |
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
| [`build_broadcast_board.py`](#build_broadcast_boardpy) | JSON табло эфира (gen + дельта) |
| [`build_playlist.py`](#build_playlistpy) | FM2-плейлист / короткий editorial |
| [`compile_route_triggers.py`](#compile_route_triggerspy) | RAM-триггеры CP: `routes.yaml` anchor → `route_triggers.yaml` |
| [`build_playthrough.py`](#build_playthroughpy) | Эталон: jsonl, routes, `cp_<head><i>.fc0` |
| [`eval_achievements.py`](#eval_achievementspy) | `tags[]` в `attempts.jsonl` |
| [`export_fm2.py`](#export_fm2py) | `inference_inputs.jsonl` → self-contained `.fm2` |
| [`hybrid_episode_prep.py`](#hybrid_episode_preppy) | Editorial + board + шаги оператора |
| [`inference_local.sh`](#inference_localsh) | Фасад: preflight → `run_inference` |
| [`inference_preflight.py`](#inference_preflightpy) | Очистка перед inference / playback |
| [`parse_train_rollouts.py`](#parse_train_rolloutspy) | Сводка `rollouts.jsonl` |
| [`play_fm2_gui.py`](#play_fm2_guipy) | GUI replay одного FM2 (отладка) |
| [`play_inference_fm2.py`](#play_inference_fm2py) | Replay FM2 или `playlist.json` |
| [`ram_scout.py`](#ram_scoutpy) | RAM scout: shell (`games/…/reference/`) или mission clear |
| [`preview_demos.py`](#preview_demospy) | PNG-превью `demos_for_bc` → `tmp/demos_for_bc/` |
| [`record_demos.py`](#record_demospy) | FM2-synced BC demos (`-playmovie`) |
| [`run_smoke.py`](#run_smokepy) | Единый smoke entry point |
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
Общие `--game` / `--mission`: если флаги опущены — из [`config/workspace.yaml`](../config/workspace.yaml) ([глоссарий](GLOSSARY.md#конфиг-рабочей-области-workspace)); иначе отказ. У многих карточек ниже не дублируются.

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

Фасад: argv → `ram_scout.run_ram_scout` (`src/ram_scout.py`).  
[Раунд разведки RAM](GLOSSARY.md#раунд-разведки-ram): FM2 → сырой scout.  
**Mission** (`games/<game>/missions/<m>/reference/*.fm2`) → плоский `reference/scout/`, затем `config/ram_resolve.json` + `ram_map.md`.  
**Shell** (`games/<game>/reference/*.fm2`) → `reference/scout/<round>/` только (якоря вручную в `env_config.yaml`).

Контекст: **scope по пути FM2** (или `clear.fm2` из [workspace](GLOSSARY.md#конфиг-рабочей-области-workspace), если путь опущен). Относительные пути — от корня репозитория. Не `cd` в миссию и не угадывание по cwd. Технический `cwd=` subprocess FCEUX — каталог staging ROM/FM2, **не** выбор плагина.

По умолчанию mission пишет только сырой scout/candidates; `ram_resolve` / `ram_map` — только с явным `--write-ram-map`.

```bash
# mission (эталон clear) — явный путь
./.venv/Scripts/python.exe scripts/ram_scout.py games/rushn_attack/missions/m1/reference/clear.fm2
# то же + запись resolve/map
./.venv/Scripts/python.exe scripts/ram_scout.py games/rushn_attack/missions/m1/reference/clear.fm2 --write-ram-map
# то же через workspace (config/workspace.yaml), без позиционного FM2
./.venv/Scripts/python.exe scripts/ram_scout.py
# shell (game over; не трогает mission scout / ram_resolve)
./.venv/Scripts/python.exe scripts/ram_scout.py games/rushn_attack/reference/game_over_to_attract.fm2
```

| Флаг | Описание |
| ---- | -------- |
| `fm2` | shell или mission layout (опционально; default — workspace `clear.fm2`) |
| `--game` / `--mission` | override workspace; при явном FM2 должны совпадать с путём |
| `--round` | id раунда (default: stem FM2); у shell — подкаталог `scout/<round>/` |
| `--timeout` | лимит секунд FCEUX (default 600) |
| `--write-ram-map` | mission: записать `ram_resolve` / `ram_map` (default: нет) |

---

### `compile_route_triggers.py`

Фасад: argv → `route_trigger_compile.compile_for_mission` (`src/route_trigger_compile.py`).  
Протокол миссии — фаза **E′**: после заполнения `frame` в `head_save_states`, до `build_playthrough`.

```bash
./.venv/Scripts/python.exe scripts/compile_route_triggers.py games/rushn_attack/missions/m1
# через workspace
./.venv/Scripts/python.exe scripts/compile_route_triggers.py
```

| Флаг | Описание |
| ---- | -------- |
| `--game` / `--mission` | override workspace |

**Вход:** `routes.yaml` (поле `anchor`), `playthrough_manifest.yaml`, `ram_scout.jsonl`, `ram_resolve.json`, `route_trigger_compile.yaml`.  
**Выход:** `config/route_triggers.yaml`.

---

### `build_playthrough.py`

После `ram_scout`: `human_playthrough.jsonl`, `playthrough_manifest.yaml`, `save_states/cp_<head><i>.fc0`. BC-демо — отдельно [`record_demos.py`](#record_demospy).

Кадры и имена `.fc0` — из `head_save_states` в манифесте (`cp_title0`, `cp_intro0`, `cp_gameplay0`, …). Train и inference reset — **один** файл (`cp_gameplay0`).  
Опциональный `games/<id>/etalon_build.yaml` — автогенерация логического `routes.yaml` + `route_triggers.yaml`; если файла нет (пилот RnA), `routes.yaml` не перезаписывается. `--states-only` etalon_build не требует.

Миссия — из пути FM2 или из workspace (`clear.fm2`), не из cwd.

```bash
./.venv/Scripts/python.exe scripts/build_playthrough.py games/rushn_attack/missions/m1/reference/clear.fm2
./.venv/Scripts/python.exe scripts/build_playthrough.py
# только переснять .fc0 по якорям манифеста (без routes/jsonl):
./.venv/Scripts/python.exe scripts/build_playthrough.py games/rushn_attack/missions/m1/reference/clear.fm2 --states-only
```

| Флаг | Описание |
| ---- | -------- |
| `fm2` | путь к FM2 (опционально; default — workspace `clear.fm2`) |
| `--game` / `--mission` | override workspace; при явном FM2 — проверка совпадения |
| `--timeout` | лимит FCEUX (default 600) |
| `--skip-states` | без `.fc0` |
| `--states-only` | только `save_states/` из `head_save_states` |
| `--replace-states` | wipe всех `*.fc0` (иначе только слоты плана) |

---

### `record_demos.py`

FM2-synced запись BC: один проход `-playmovie clear.fm2` → `reference/demos_for_bc/seg_*.npz`. Quality gate встроен.

```bash
./.venv/Scripts/python.exe scripts/record_demos.py --game rushn_attack --mission m1
```

| Флаг | Описание |
| ---- | -------- |
| `fm2` | путь к FM2 (опционально) |
| `--game` / `--mission` | override workspace |
| `--segment ID` | только указанные сегменты |
| `--no-strict-quality` | не прерывать при провале quality gate |
| `--timeout` | таймаут FCEUX (сек, default 600) |

---

### `preview_demos.py`

PNG-превью и приёмка BC (`--check` → exit 1 при провале quality gate).

```bash
./.venv/Scripts/python.exe scripts/preview_demos.py --game rushn_attack --mission m1 --check
./.venv/Scripts/python.exe scripts/preview_demos.py --segment seg_002 --step-interval 10
```

| Флаг | Описание |
| ---- | -------- |
| `--game` / `--mission` | миссия (default — workspace) |
| `--out` | каталог вывода (default `tmp/demos_for_bc/`) |
| `--segment ID` | только указанные сегменты (можно несколько раз) |
| `--step-interval` | шаг env между sample PNG (default 25) |
| `--max-samples` | макс. шагов для samples на сегмент (default 200) |
| `--grid-cols` | сторона сетки `grid.png` (default 5 → 5×5) |
| `--tile-px` | размер плитки в сетке (default 112) |
| `--check` | exit 1 если quality gate не пройден |

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

Smoke IPC `FceuxBridge` (нужен `save_states/cp_gameplay0.fc0` или `cp_gameplay1.fc0`). CLI нет.

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
| `--save-state` | относительно миссии (default `save_states/cp_gameplay0.fc0`) |
| `--session` | id bridge (default `smoke_env`) |
| `--death-mode` | `life_lost` \| `game_over` (override `env_config.yaml`; H3) |
| `--log` | append в `logs/smoke/attempts.jsonl` |
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
| `--save-state` | default `save_states/cp_gameplay0.fc0` |
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
Модуль BC: `src/train/bc_pretrain.py` (при `--bc-epochs > 0`; demos проходят quality gate).

```bash
./scripts/train_local.sh --timesteps 50000 --model-out models/gen0.zip
./.venv/Scripts/python.exe src/train/train_ppo.py --smoke --timesteps 256 --n-envs 1 --dummy-vec --no-bc
```

| Флаг | Описание |
| ---- | -------- |
| `--task` | `tasks/train_task.json` |
| `--timesteps` | total steps (default 500000) |
| `--allow-reduce-target` | continue: разрешить `--timesteps` ниже sidecar |
| `--n-envs` | parallel FCEUX (default **8**; через `train_local.sh` → **6**) |
| `--model-in` / `--model-out` | предок / артефакт поколения (default out: `models/gen0.zip`) |
| `--overwrite-model-out` | явно заменить существующий `model-out` (scratch или from_ancestor) |
| `--latest-model` / `--no-latest-model` | `models/latest.zip` (default on) |
| `--latest-every` | latest.zip каждые N rollout (default **5**, H5; `1` = каждый) |
| `--recycle-every-timesteps` | H4: пересоздать FCEUX/vec каждые N steps (`0`=off) |
| `--session-wall-timeout` | H6: abort по wall-clock сессии, с (`0`=off; continue из model zip) |
| `--save-every` | каждые N steps (default 50000) |
| `--bc-epochs` / `--bc-demo` / `--no-bc` | BC warm-start; **`--timesteps 0`** — только BC, сохранение `saved (bc_only)` + offline `BC demo match` |
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

**Режимы model-out (безопасно по умолчанию):**

| Ситуация | Режим |
| -------- | ----- |
| `model-out` есть, `--model-in` нет | **continue** — добор того же поколения (timesteps из sidecar/zip, без повторного BC) |
| `--model-in` → другой новый `model-out` | **from_ancestor** — веса предка, счётчик поколения с 0; BC по флагам |
| `model-out` нет, `--model-in` нет | **scratch** — новая сеть |
| `model-out` уже есть и нужен replace | только с **`--overwrite-model-out`** (иначе `SystemExit`) |
| `--model-in` = `--model-out` | отказ — для continue уберите `--model-in` |

```bash
# continue gen0
./scripts/train_local.sh --model-out models/gen0.zip --timesteps 1700000 --no-bc

# новое поколение от предка (gen1 ещё не существует)
./scripts/train_local.sh --model-in models/gen0.zip --model-out models/gen1.zip --timesteps 300000 --bc-epochs 5

# явно затереть out
./scripts/train_local.sh --model-out models/gen1.zip --overwrite-model-out --no-bc --timesteps 10000
```

Continue / прерывание: Ctrl+C/SIGTERM → атомарный save + sidecar; повтор с тем же `--model-out` (без `--model-in`) продолжает до `target_timesteps`. CLI `--timesteps` больше sidecar → цель поднимается. Явный `--timesteps` **ниже** sidecar → отказ, пока нет `--allow-reduce-target` (дефолт argparse без флага не укорачивает). Смена `--n-envs` на continue разрешена (hardware-ключ; sidecar обновляет `n_envs` последнего прогона, timesteps не сбрасываются). Task JSON заполняет только поля, не заданные в CLI (`checkpoint_*` deprecated → `model_*`).
Автостоп схлопа политики (по умолчанию): ≥10 rollout подряд с `|entropy_loss|<0.01` и `approx_kl≈0` → выход `learn`, save `model-out` (`policy_collapse`); см. [TRAIN_ANALYSIS](TRAIN_ANALYSIS.md#практическое-правило-остановки-политика).

---

### `train_fps_round_prep.py`

Архив `models/gen0.zip` + печать команд для fps/dual-train раунда. Runbook — [TASK_TRAIN_FPS_DEGRADATION](tasks/archive/TASK_TRAIN_FPS_DEGRADATION.md).

```bash
./.venv/Scripts/python.exe scripts/train_fps_round_prep.py
```

| Флаг | Описание |
| ---- | -------- |
| `--target-timesteps` | цель для continue `models/gen0.zip` (default 100k) |
| `--session` | метка metrics-сессии в `tmp/bench/` |
| `--game` / `--mission` | override workspace |

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

Перед inference: staging/bridge; **пул поколения по умолчанию сохраняется** (печатает текущий airtime). Wipe — только по флагу. Вызывается из `inference_local.sh` / `play_inference_fm2`.

```bash
./.venv/Scripts/python.exe scripts/inference_preflight.py --model gen0.zip
./.venv/Scripts/python.exe scripts/inference_preflight.py --model gen0.zip --wipe-gen-logs
./.venv/Scripts/python.exe scripts/inference_preflight.py --playback-only
```

| Флаг | Описание |
| ---- | -------- |
| `--playback-only` | только staging/bridge (для replay, без wipe logs) |
| `--wipe-gen-logs` | удалить `logs/<model_version>/` перед сбором |
| `--model` / `--model-version` | stem пула (иначе `models/latest.zip`) |
| `--game` / `--mission` | |

---

### `inference_local.sh`

Фасад: preflight → `run_inference`. Два сценария:

| Сценарий | Как вызвать | Что делает |
| -------- | ----------- | ---------- |
| **Pool** | без `--live` | `--playlist-cnt N` попыток → `logs/genN/` + ачивки + плейлист |
| **Live** | `--live` | окно FCEUX до Ctrl+C, **без** записи пула |

Без аргументов — pool: `--playlist-cnt 5`, `--stochastic`. Свои флаги оболочки: `--skip-preflight`, `--wipe-gen-logs`. `--wipe-gen-logs` / `--playlist-cnt` нельзя с `--live`. Wipe + `--skip-preflight` — ошибка. `--model` и `--model-version` с разным stem — отказ.

```bash
# Pool: пул + плейлист
./scripts/inference_local.sh
./scripts/inference_local.sh --model gen0.zip --playlist-cnt 13 --wipe-gen-logs

# Live: эфир до Ctrl+C (без пула)
./scripts/inference_local.sh --live --model gen0.zip

# Hybrid editorial + board (после накопления пула)
./.venv/Scripts/python.exe scripts/hybrid_episode_prep.py --model gen0.zip
```

| Флаг оболочки | Описание |
| ------------- | -------- |
| `--live` | сценарий эфира (пробрасывается в `run_inference`) |
| `--skip-preflight` | не вызывать `inference_preflight` |
| `--wipe-gen-logs` | pool: снести `logs/<model_version>/` перед сбором |

---

### `run_inference.py`

<a id="inference"></a>
<a id="run_inferencepy"></a>

Локальный PPO inference. Два взаимоисключающих режима:

- **Pool** (по умолчанию): `--playlist-cnt N` попыток → `games/.../logs/<model_version>/` (`attempts.jsonl`, `inference_inputs.jsonl`), теги ачивок, **всегда** сборка плейлиста.
- **Live** (`--live`): окно FCEUX + `fceux/operator/fceux.cfg` до Ctrl+C, **без** записи в `logs/genN/`. Нельзя с `--playlist-cnt` / `--wipe-gen-logs` / `--playlist-no-dedupe`.

`model_version` = stem модели (`gen0` из `gen0.zip`). Default save state: `save_states/cp_gameplay0.fc0`. Пул — [пул поколения](GLOSSARY.md#пул-поколения); эфир — [STREAMING_CONCEPT.md](STREAMING_CONCEPT.md). Multi-head — один zip ([TASK_POLICY_SEPARATION](tasks/archive/TASK_POLICY_SEPARATION.md)).

```bash
# Pool: N попыток + плейлист
./.venv/Scripts/python.exe src/stream/run_inference.py \
  --model gen0.zip --playlist-cnt 5 --stochastic

# Live: окно до Ctrl+C, без пула
./.venv/Scripts/python.exe src/stream/run_inference.py \
  --model gen0.zip --live --stochastic
```

| Флаг | Описание |
| ---- | -------- |
| `--model` | один `.zip` в `models/` (default `gen0.zip`); Multi-head — тот же путь |
| `--live` | эфир до Ctrl+C, без `logs/genN/` |
| `--playlist-cnt` | pool: число попыток перед плейлистом (default 5; нельзя с `--live`) |
| `--max-steps` | default 8000 |
| `--stochastic` | sampling (рекомендуется vs greedy) |
| `--save-state` | reset state (default `cp_gameplay0.fc0`) |
| `--playlist-no-dedupe` | pool: без дедупа (нельзя с `--live`) |
| `--fceux-profile` | default `inference` |
| `--turbo` | force turbo on (live по умолчанию выкл) |
| `--session` | id bridge (default `inference`) |
| `--reward-profile` / `--model-version` | |
| `--wipe-gen-logs` | pool: wipe перед сбором (нельзя с `--live`) |
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
| `--input` | jsonl (default — `logs/<model_version>/inference_inputs.jsonl`) |
| `--model` / `--model-version` | stem пула, если нет `--input` |
| `--episode` | один эпизод |
| `--frame-skip` | NES-кадров на env step (default 4) |
| `--template` | заголовок FM2 |
| `--save-state` | `.fc0` для embed (default `cp_gameplay0.fc0`) |
| `--game` / `--mission` | |

---

### `eval_achievements.py`

Правила [`games/<game>/achievements.yaml`](../games/rushn_attack/achievements.yaml) (путь из `game.yaml`) → `tags[]` в attempts. Номинации пилота — [GAME_RUSHN_ATTACK.md §5](GAME_RUSHN_ATTACK.md#5-achievements-номинации-пилота).

```bash
./.venv/Scripts/python.exe scripts/eval_achievements.py --model gen0.zip
```

| Флаг | Описание |
| ---- | -------- |
| `--attempts` | путь к attempts (default — `logs/<model_version>/attempts.jsonl`) |
| `--model` / `--model-version` | stem пула, если нет `--attempts` |
| `--config` | путь к YAML |
| `--game` / `--mission` | |

---

### `build_playlist.py`

<a id="achievements-и-плейлист"></a>

Attempts (+ опц. inputs) → `NN_slug_MMM.fm2`, `.overlay.json`, `playlist.json` (поле `airtime`), `playlist.play.cmd`.  
Кандидаты — из [пула поколения](GLOSSARY.md#пул-поколения); длина editorial — [airtime](GLOSSARY.md#airtime).  
Режиссёрский сценарий hybrid: `--editorial` (порядок `editorial_order`, потолок ~12 мин / `max_clips`).

```bash
# Короткий editorial (дефолт hybrid)
./.venv/Scripts/python.exe scripts/build_playlist.py --model gen0.zip --editorial
./.venv/Scripts/python.exe scripts/build_playlist.py --model gen0.zip --editorial --max-airtime 8m --max-clips 10

# Полная пересборка по broadcast_order (без лимита editorial)
./.venv/Scripts/python.exe scripts/build_playlist.py --model gen0.zip
./.venv/Scripts/python.exe scripts/build_playlist.py --inputs logs/gen0/inference_inputs.jsonl
```

| Флаг | Описание |
| ---- | -------- |
| `--editorial` | короткий пакет: `editorial_order` + лимиты |
| `--max-airtime` | потолок airtime (`12m`, `8m`, …); с `--editorial` дефолт из YAML |
| `--max-clips` / `--max-per-slug` | потолки числа клипов |
| `--attempts` | attempts.jsonl |
| `--inputs` | on-demand FM2 из inputs |
| `--model` / `--model-version` | stem пула, если нет `--attempts` |
| `--no-dedupe` | не пропускать дубликаты эпизодов |
| `--game` / `--mission` | |

Выход в `logs/<model_version>/`: `.fm2` (embed savestate), `.overlay.json`, `playlist.json` (+ `airtime`, `model_version`, при editorial — `kind`), `.play.cmd`.

---

### `build_broadcast_board.py`

<a id="build_broadcast_boardpy"></a>

Агрегаты `logs/genN/attempts.jsonl` (+ дельта vs `genN−1`) → `broadcast_board.json` для OBS Browser Source (`streaming/board/`).

```bash
./.venv/Scripts/python.exe scripts/build_broadcast_board.py --model gen1.zip --mode open
./.venv/Scripts/python.exe scripts/build_broadcast_board.py --model gen1.zip --mode live --no-support-line
```

| Флаг | Описание |
| ---- | -------- |
| `--mode` | `open` / `editorial` / `live` / `close` / `frontier_report` |
| `--model` / `--model-version` | stem пула |
| `--support-line` / `--no-support-line` | скромная строка поддержки |
| `--output` | один путь JSON (иначе pool + `streaming/board/`) |
| `--game` / `--mission` | |

Поля JSON: `model_version`, `frontier`, `eval.reach_cp`, `delta` (frontier / clear rate / wall), `mode`, опц. `support_line`. Без CTA «донать на GPU / ETA».

---

### `hybrid_episode_prep.py`

<a id="hybrid_episode_preppy"></a>

Один вызов: `--editorial` playlist + `broadcast_board.json` + печать операторского потока Board → editorial → Board → live → Board.

```bash
./.venv/Scripts/python.exe scripts/hybrid_episode_prep.py --model gen1.zip
./.venv/Scripts/python.exe scripts/hybrid_episode_prep.py --model gen1.zip --max-airtime 8m --mode open
```

| Флаг | Описание |
| ---- | -------- |
| `--max-airtime` / `--max-clips` | лимиты editorial |
| `--mode` | начальный mode board |
| `--no-support-line` | без строки поддержки |
| `--model` / `--model-version` | |
| `--game` / `--mission` | |

Board в браузере: `streaming/board/index.html` (читает соседний `broadcast_board.json`). Live: `run_inference --live`.

---

### `play_inference_fm2.py`

Фасад: argv → `stream.play_fm2.play_input` (хелперы staging/wait — `fm2_playback`).  
Replay одного self-contained `.fm2` или всего `playlist.json` (эфир).

```bash
# После сбора (genN = stem модели)
./.venv/Scripts/python.exe scripts/play_inference_fm2.py \
  games/rushn_attack/missions/m1/logs/gen0/playlist.json
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

Фасад: argv → `stream.play_fm2.play_gui_fm2`.  
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
