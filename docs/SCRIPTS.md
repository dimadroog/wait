# SCRIPTS — каталог консольных entry point'ов

> Запуск из корня репозитория.  
> Python: `.venv\Scripts\python.exe` (или активированный `.venv`).

**Область документа:** только скрипты и CLI entry point'ы (`scripts/*`, `src/train/train_ppo.py`, `src/stream/run_inference.py`) — назначение, типовая команда, вход/выход, флаги.

**Не писать сюда:** замеры FPS/ms, таблицы baseline, backlog-номера этапов, runbook расследований, описания контрактов данных, pytest-сюиты.  
→ контракты: [ML_CONCEPT.md §8](ML_CONCEPT.md#8-форматы-данных) · задачи: [TASK_BLANK](tasks/TASK_BLANK.md) · гигиена: [DESIGN.md](DESIGN.md#гигиена-артефактов).

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
| Диагностика BC open-loop vs closed-loop | [`bc_open_loop_eval.py`](#bc_open_loop_evalpy) |
| BC open-loop watch в FCEUX (max match) | [`bc_open_loop_watch.py`](#bc_open_loop_watchpy) |
| Сравнить NPZ obs vs live env | [`bc_obs_compare.py`](#bc_obs_comparepy) |
| Smoke после правок bridge/env | [`run_smoke.py`](#run_smokepy) |
| Обучение PPO | [`train_local.sh`](#train_localsh) → [`train_ppo.py`](#train_ppopy) |
| Inference pool (`--episodes N`) или live (до Ctrl+C) | [`inference_local.sh`](#inference_localsh) → [`run_inference.py`](#run_inferencepy) |
| Replay одного `.fm2` | [`play_inference_fm2.py`](#play_inference_fm2py) |
| Операторский GUI (Config / Inference / Train) | [`operator_launcher.py`](#operator_launcherpy) |

---

## Индекс

| Скрипт | Назначение |
| ------ | ---------- |
| [`bc_obs_compare.py`](#bc_obs_comparepy) | NPZ vs live env obs diff на human-траектории |
| [`bc_open_loop_eval.py`](#bc_open_loop_evalpy) | BC transfer diagnostic: open-loop + closed-loop match |
| [`bc_open_loop_watch.py`](#bc_open_loop_watchpy) | BC open-loop watch: FCEUX + pred vs human |
| [`compile_route_triggers.py`](#compile_route_triggerspy) | RAM-триггеры CP: `routes.yaml` anchor → `route_triggers.yaml` |
| [`build_playthrough.py`](#build_playthroughpy) | Эталон: jsonl, routes, `cp_<head><i>.fc0` |
| [`export_fm2.py`](#export_fm2py) | `inference_inputs.jsonl` → self-contained `.fm2` |
| [`inference_local.sh`](#inference_localsh) | Фасад: preflight → `run_inference` |
| [`inference_preflight.py`](#inference_preflightpy) | Очистка перед inference / playback |
| [`operator_launcher.py`](#operator_launcherpy) | GUI: workspace + inference + train (subprocess фасады) |
| [`ram_scout.py`](#ram_scoutpy) | RAM scout: shell (`games/…/reference/`) или mission clear |
| [`preview_demos.py`](#preview_demospy) | PNG-превью `demos_for_bc` → `tmp/demos_for_bc/` |
| [`record_demos.py`](#record_demospy) | FM2-synced BC demos (`-playmovie`) |
| [`run_smoke.py`](#run_smokepy) | Единый smoke entry point |
| [`setup_all.ps1`](#setup_allps1) | Setup: venv (+ FCEUX вручную) |
| [`setup_venv.ps1`](#setup_venvps1) | Создать `.venv`, `requirements.txt` |
| [`smoke_bridge.py`](#smoke_bridgepy) | Smoke IPC bridge |
| [`smoke_env.py`](#smoke_envpy) | Smoke Gymnasium env |
| [`test_parallel_env.py`](#test_parallel_envpy) | Parallel vec step + reset |
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

### `bc_obs_compare.py`

Побайтовое сравнение obs из `demos_for_bc/seg_*.npz` и live env на human-траектории. Отчёт → `tmp/bench/bc_obs_compare/`.

```bash
./.venv/Scripts/python.exe scripts/bc_obs_compare.py \
  --game rushn_attack --mission m1 \
  --model tmp/bench/bc_sanity_overfit/bc_sanity_overfit.zip
```

---

### `bc_open_loop_eval.py`

Диагностика переноса BC: greedy open-loop match на human-траектории (FCEUX) и/или closed-loop сравнение с `inference_inputs.jsonl`. Отчёты → `tmp/bench/…`.

```bash
./.venv/Scripts/python.exe scripts/bc_open_loop_eval.py \
  --game rushn_attack --mission m1 \
  --model tmp/bench/bc_sanity_overfit/bc_sanity_overfit.zip \
  --closed-loop-logs games/rushn_attack/missions/m1/logs/bc_sanity_overfit/inference_inputs.jsonl \
  --out tmp/bench/bc_open_loop_overfit
```

| Флаг | Описание |
| ---- | -------- |
| `--model` | путь к `.zip` (обязателен без `--no-fceux`) |
| `--frame-start` / `--frame-end` | диапазон decision-кадров (default 1034–1300) |
| `--attack-window` | окно атаки `START-END` (default `1195-1210`) |
| `--closed-loop-logs` | `inference_inputs.jsonl` для closed-loop без FCEUX |
| `--no-fceux` | только closed-loop часть |
| `--segment` | NPZ-сегмент для offline baseline (default `seg_002`) |
| `--out` | каталог отчётов (default `tmp/bench/bc_open_loop`) |
| `--run-label` | метка в `bc_transfer_verdict.md` |

Ядро: `src/bc_open_loop_eval.py`.

---

### `bc_open_loop_watch.py`

BC open-loop **watch**: human ведёт gameplay в окне FCEUX, в консоли greedy pred vs human (`OK`/`MISS`). Максимальное соответствие BC в gameplay (~80% live); не `run_inference` (closed-loop).

```bash
./.venv/Scripts/python.exe scripts/bc_open_loop_watch.py \
  --game rushn_attack --mission m1 \
  --model tmp/bench/bc_sanity_overfit/bc_sanity_overfit.zip
```

Короткий прогон (attack-window):

```bash
./.venv/Scripts/python.exe scripts/bc_open_loop_watch.py \
  --game rushn_attack --mission m1 \
  --model tmp/bench/bc_sanity_overfit/bc_sanity_overfit.zip \
  --frame-start 1180 --frame-end 1230
```

| Флаг | Описание |
| ---- | -------- |
| `--model` | путь к BC `.zip` (обязателен) |
| `--frame-start` / `--frame-end` | диапазон (default 1034–1300) |
| `--frame-skip` | decision cadence (default 4) |
| `--attack-window` | окно атаки для метки `attack` в логе |
| `--save-state` | default `save_states/cp_gameplay0.fc0` |
| `--no-window` | headless (быстрая проверка без окна) |
| `--realtime` | без turbo (медленно, каждый NES-кадр) |

Turbo **включён** по умолчанию. Без NPZ offline / отчётов — только watch.

---

### `run_smoke.py`

Единый smoke после правок bridge/env. Subprocess: `smoke_bridge`, `smoke_env --steps 20`, `test_parallel_env`. Exit 0/1; cleanup quarantine в `finally`.

```bash
./.venv/Scripts/python.exe scripts/run_smoke.py
./.venv/Scripts/python.exe scripts/run_smoke.py --suite bridge,env,parallel
```

| Флаг | Описание |
| ---- | -------- |
| `--suite` | `bridge`, `env`, `parallel` (default — все три) |

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
./.venv/Scripts/python.exe src/train/train_ppo.py --smoke --timesteps 256 --n-envs 1 --dummy-vec
```

| Флаг | Описание |
| ---- | -------- |
| `--task` | `tasks/train_task.json` |
| `--timesteps` | total steps (default 500000) |
| `--allow-reduce-target` | continue: разрешить `--timesteps` ниже sidecar (**опасно**) |
| `--n-envs` | parallel FCEUX (default **8**; через `train_local.sh` → **6**) |
| `--model-in` / `--model-out` | предок / артефакт поколения (default out: `models/gen0.zip`) |
| `--scratch` | пересоздать сеть на существующем `model-out` (snapshot в `.prev` перед сессией) |
| `--rollback` | откатить последний прогон: `genN.prev.*` → `genN.*` (без train) |
| `--latest-model` / `--no-latest-model` | `models/{stem}.latest.zip` (default on) |
| `--latest-every` | latest каждые N rollout (default **5**; `1` = каждый) |
| `--save-every` | каждые N steps (default 50000) |
| `--bc-epochs` / `--bc-demo` | BC; на **continue** — refresh при `--bc-epochs > 0`; **`--timesteps 0`** — только BC |
| `--rollout-gc` / `--no-rollout-gc` | `gc.collect` после rollout (default on) |
| `--smoke` / `--smoke-session` | карантин `tmp/smoke/` |
| `--no-intermediate-models` | без `models/runs/` |
| `--dummy-vec` | DummyVecEnv |
| `--no-turbo` | отладка |
| `--no-progress-pct` | не писать `progress_pct` / `target_timesteps` в таблицу SB3 |
| `--learn-stall-timeout` | abort без прогресса timesteps (default 300; `0`=off) |
| `--skip-preflight` | не вызывать preflight (только прямой вызов) |
| `--n-steps`, `--batch-size`, `--n-epochs`, `--gamma`, `--learning-rate`, `--threads` | PPO гиперпараметры |
| `--save-state`, `--reward-profile`, `--game`, `--mission` | |
| `--death-mode` | `life_lost` \| `game_over` (default из `env_config.yaml`) |

**Режимы model-out:**

| Ситуация | Режим |
| -------- | ----- |
| `model-out` есть, без `--scratch` / `--model-in` | **continue** — добор поколения; snapshot `.prev` перед сессией |
| то же + `--bc-epochs N` | continue + BC refresh |
| `--model-in` → новый `model-out` (out не существует) | **from_ancestor** — новое поколение; `--timesteps` абсолютная цель |
| `model-out` нет | **scratch** — новая сеть |
| `model-out` есть + `--scratch` | scratch на том же пути (snapshot `.prev`) |
| `--rollback --model-out genN.zip` | восстановить из `.prev`, без train |

```bash
# continue + BC refresh (цель 500k → 600k)
./scripts/train_local.sh --model-out models/gen0.zip --timesteps 600000 --bc-epochs 2

# откат последнего прогона
./scripts/train_local.sh --rollback --model-out models/gen0.zip

# новое поколение
./scripts/train_local.sh --model-in models/gen0.zip --model-out models/gen1.zip --timesteps 300000 --bc-epochs 5

# пересоздать gen0
./scripts/train_local.sh --scratch --model-out models/gen0.zip --timesteps 500000 --bc-epochs 5
```

Перед каждой сессией continue/scratch на существующем `genN.zip` пишется **`genN.prev.zip`** (+ sidecar) — один уровень отката через `--rollback`.

Continue / прерывание: Ctrl+C/SIGTERM → атомарный save + sidecar. CLI `--timesteps` выше sidecar поднимает цель; ниже — только с `--allow-reduce-target`. Смена `--n-envs` на continue разрешена.
Автостоп схлопа политики (по умолчанию): ≥10 rollout подряд с `|entropy_loss|<0.01` и `approx_kl≈0` → выход `learn`, save `model-out` (`policy_collapse`); см. [TRAIN_ANALYSIS](TRAIN_ANALYSIS.md#практическое-правило-остановки-политика).

---

### `inference_preflight.py`

Перед inference: staging/bridge; **пул поколения по умолчанию сохраняется**. Wipe — только по флагу. Вызывается из `inference_local.sh` / `play_inference_fm2`.

```bash
./.venv/Scripts/python.exe scripts/inference_preflight.py --model gen0.zip
./.venv/Scripts/python.exe scripts/inference_preflight.py --model gen0.zip --wipe-gen-logs
./.venv/Scripts/python.exe scripts/inference_preflight.py --playback-only
```

| Флаг | Описание |
| ---- | -------- |
| `--playback-only` | только staging/bridge (для replay, без wipe logs) |
| `--wipe-gen-logs` | удалить `logs/<model_version>/` перед сбором |
| `--model` / `--model-version` | stem пула (иначе `models/genN.zip` / `genN.latest.zip`) |
| `--game` / `--mission` | |

---

### `inference_local.sh`

Фасад: preflight → `run_inference`. Два сценария:

| Сценарий | Как вызвать | Что делает |
| -------- | ----------- | ---------- |
| **Pool** | без `--live` | `--episodes N` попыток → `logs/genN/` (`attempts.jsonl`, `inference_inputs.jsonl`) |
| **Live** | `--live` | окно FCEUX до Ctrl+C, **без** записи пула |

Без аргументов — pool: `--episodes 5`, `--stochastic`. Свои флаги оболочки: `--skip-preflight`, `--wipe-gen-logs`. `--wipe-gen-logs` / `--episodes` нельзя с `--live`. Wipe + `--skip-preflight` — ошибка. `--model` и `--model-version` с разным stem — отказ.

```bash
# Pool: N попыток в logs/genN/
./scripts/inference_local.sh
./scripts/inference_local.sh --model gen0.zip --episodes 13 --wipe-gen-logs

# Live: эфир до Ctrl+C (без пула)
./scripts/inference_local.sh --live --model gen0.zip
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

- **Pool** (по умолчанию): `--episodes N` попыток → `games/.../logs/<model_version>/` (`attempts.jsonl`, `inference_inputs.jsonl`).
- **Live** (`--live`): окно FCEUX + `fceux/operator/fceux.cfg` до Ctrl+C, **без** записи в `logs/genN/`. Нельзя с `--episodes` / `--wipe-gen-logs`.

`model_version` = stem модели (`gen0` из `gen0.zip`). Default save state: `save_states/cp_gameplay0.fc0`. Пул — [пул поколения](GLOSSARY.md#пул-поколения); эфир — [STREAMING_CONCEPT.md](STREAMING_CONCEPT.md). Multi-head — один zip.

```bash
# Pool: N попыток в logs/genN/
./.venv/Scripts/python.exe src/stream/run_inference.py \
  --model gen0.zip --episodes 5 --stochastic

# Live: окно до Ctrl+C, без пула
./.venv/Scripts/python.exe src/stream/run_inference.py \
  --model gen0.zip --live --stochastic
```

| Флаг | Описание |
| ---- | -------- |
| `--model` | один `.zip` в `models/` (default `gen0.zip`); Multi-head — тот же путь |
| `--live` | эфир до Ctrl+C, без `logs/genN/` |
| `--episodes` | pool: число попыток (default 5; нельзя с `--live`) |
| `--max-steps` | default 8000 |
| `--stochastic` | sampling (рекомендуется vs greedy) |
| `--save-state` | reset state (default `cp_gameplay0.fc0`) |
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

### `operator_launcher.py`

<a id="operator_launcherpy"></a>

Операторский GUI (Tkinter): смена рабочего контекста (`config/workspace.yaml`: game / mission / save_state) и запуск inference / train через subprocess-фасады. Бизнес-логика train/inference **не** в GUI — только сбор argv и панель stdout.

```bash
./.venv/Scripts/python.exe scripts/operator_launcher.py
```

Windows (двойной клик или из cmd):

```bat
operator_launcher.cmd
```

| Область | Действия |
| ------- | -------- |
| **Config** | game, mission, чекпоинт миссии (`save_state`); кнопка «Применить» → `workspace.yaml` |
| **Inference** | `mode`: live / pool / replay; live+pool → preflight + `run_inference`; replay → `play_inference_fm2.py` (один `.fm2`) |
| **Train** | `continue` / `scratch` / `from_ancestor` → preflight + `train_ppo` |
| **Rollback** | `genN.prev.zip` → `genN.zip` (без learn) |

Лаунчер вызывает те же шаги, что `inference_local.sh` / `train_local.sh`, через **venv Python** (не `bash` — на Windows `bash` из System32 это WSL-заглушка). Под формами — **предпросмотр команды** (копировать в терминал).

---

### `play_inference_fm2.py`

Фасад: argv → `stream.play_fm2.play_input` (хелперы staging/wait — `fm2_playback`).  
Replay одного self-contained `.fm2` (без playlist / overlay HUD).

```bash
./.venv/Scripts/python.exe scripts/play_inference_fm2.py path/to/clip.fm2
```

| Флаг | Описание |
| ---- | -------- |
| `input` | путь к `.fm2` |
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

- [DESIGN.md § Структура репозитория](DESIGN.md#структура-репозитория) · [гигиена](DESIGN.md#гигиена-артефактов)
- [ML_CONCEPT.md §8](ML_CONCEPT.md#8-форматы-данных) — контракты данных
