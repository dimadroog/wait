# TASK_OPERATOR_LAUNCHER — операторский GUI-лаунчер

**Статус:** in progress  
**Приоритет:** medium  
**Ветка:** `task/operator-launcher` — проработку и код выполнять **только в этой ветке** (не в `main` и не в чужих task-ветках). Если ветки нет: `git checkout -b task/operator-launcher` от актуального `main`.  
**Зависит от:** [контракт game/mission](../DESIGN.md#контракт-game--mission) (`config/workspace.yaml`, `resolve_game_mission`); фасады [`inference_local.sh`](../SCRIPTS.md#inference_localsh), [`train_local.sh`](../SCRIPTS.md#train_localsh)  
**Файлы:** `config/workspace.yaml`, `src/project_paths.py`, `src/operator_launcher/` (новый пакет), `scripts/operator_launcher.py`, `scripts/inference_local.sh`, `scripts/train_local.sh`, `docs/SCRIPTS.md`  
**Контекст в чат:** `@docs/tasks/TASK_OPERATOR_LAUNCHER.md` + шпаргалка ниже (не `docs/tasks/archive/`).

Каркас: [TASK_BLANK.md](TASK_BLANK.md)

### Состояние реализации

| Что | Статус |
| --- | ------ |
| Спецификация UI (Config / Inference / Train) | **утверждена** — § «Спецификация UI» |
| План клиента (Tkinter) | **утверждён** — § «План реализации клиента» |
| `src/operator_launcher/` | **создан** |
| `scripts/operator_launcher.py` | **создан** |
| `config/workspace.yaml` | `game` / `mission` / `save_state` |
| Регистрация в SCRIPTS.md | **да** |

**Следующий шаг для агента:** ручная приёмка на `games/rushn_attack/missions/m1/` (этап 7).

### Шпаргалка для агента (порядок чтения)

| Файл | Зачем |
| ---- | ----- |
| Этот TASK | Контракт UI, план, DoD, антискоуп |
| [DESIGN.md § контракт game/mission](../DESIGN.md#контракт-game--mission) | workspace, без cwd-гибрида |
| [pluggable-core.mdc](../../.cursor/rules/pluggable-core.mdc) | нет `if game_id`, enum из layout |
| [artifact-hygiene.mdc](../../.cursor/rules/artifact-hygiene.mdc) | не писать smoke в `games/…/models/` |
| `src/project_paths.py` | `repo_root`, `mission_dir`, `load_workspace`, `load_yaml` |
| `src/inference_states.py` | дефолт save_state для миссии |
| `src/playthrough_build.py` | `load_head_save_states` |
| `scripts/train_local.sh`, `scripts/inference_local.sh` | фасады preflight + argv |
| `src/stream/run_inference.py` | `validate_inference_args` (live vs pool) |
| `src/train/train_ppo.py` | `build_parser`, режимы model-out |
| [SCRIPTS.md](../SCRIPTS.md) | карточки train / inference / play_inference_fm2 |
| [TRAIN_ANALYSIS.md](../TRAIN_ANALYSIS.md) | что оператор видит в stdout train |

Пилот для ручной приёмки: `games/rushn_attack/missions/m1/`.

### Контракт subprocess (Windows)

Лаунчер **не** переносит логику preflight/train/inference — только argv и `cwd=repo_root()`.

- Python venv: `./.venv/Scripts/python.exe` (прямой вызов; **не** `bash` из System32 — WSL-заглушка).
- Inference/train: две фазы — `*_preflight.py` → `run_inference.py` / `train_ppo.py` (эквивалент shell-фасадов).
- Replay: `scripts/play_inference_fm2.py` (один `.fm2`).
- Всегда явно: `--game`, `--mission`, `--save-state` (кроме rollback).
- Стоп inference/replay: `taskkill /T` + cleanup orphan FCEUX; train — graceful Ctrl+Break.

Пример сборки (логика в `commands.py`, не в UI):

```text
# pool inference (фаза 1: inference_preflight.py; фаза 2: run_inference.py)
.venv/Scripts/python.exe scripts/inference_preflight.py --game rushn_attack --mission m1 --model gen0.zip
.venv/Scripts/python.exe src/stream/run_inference.py --skip-preflight --model gen0.zip --episodes 5 ...

# train continue (фаза 1: train_preflight.py; фаза 2: train_ppo.py)
.venv/Scripts/python.exe scripts/train_preflight.py
.venv/Scripts/python.exe src/train/train_ppo.py --n-envs 6 --model-out models/gen0.zip ...
```

Запуск GUI после реализации: `./.venv/Scripts/python.exe scripts/operator_launcher.py`

### Промпт для нового контекста

Скопировать в чат с агентом (одно окно ≈ один этап из чеклиста):

```text
Выполни TASK_OPERATOR_LAUNCHER в ветке task/operator-launcher.

Контекст: @docs/tasks/TASK_OPERATOR_LAUNCHER.md (прочитать целиком: состояние, шпаргалка, спецификация, план, чеклист).

Сейчас: этап N из чеклиста (смотри «Состояние реализации» — что уже [x]).

Стек: Tkinter, без новых зависимостей. Фасад subprocess — train_local.sh / inference_local.sh / play_inference_fm2.py. Логика train/inference не в GUI.

Ограничения: pluggable-core (enum из games/*, без if game_id); artifact-hygiene; scripts/ — тонкий фасад.

После этапа: отметить чеклист в TASK, не коммитить без запроса.
```

### Цель

Дать оператору единое GUI для смены рабочего контекста (игра / миссия / стартовый save state) и запуска трёх сценариев без ручного набора CLI: **Inference** (live / pool / replay), **Train**. Лаунчер не дублирует бизнес-логику train/inference — только резолв конфига, сбор argv и subprocess с выводом в панель лога.

### Спецификация UI (утверждено)

#### Config

- `game` — enum из `games/*/game.yaml` (`game_id` + `title`); дефолт: `workspace.game`.
- `mission` — enum из `games/<game>/missions/*`; дефолт: `workspace.mission` или `game.yaml → default_mission`.
- `save_state` (UI: «чекпоинт миссии») — enum якорей `head_save_states` в `playthrough_manifest.yaml` (группы title / intro / gameplay / bossfight); подписи CP — из `routes.yaml` где есть `anchor`; значение — путь `save_states/<anchor>.fc0` относительно миссии; дефолт: `inference.save_state` → `train.save_state` → `save_states/cp_gameplay0.fc0` (как `resolve_inference_reset_state`). Не путать с `models/genN.zip`.
- Persistence: `config/workspace.yaml`; резолв CLI > workspace ([DESIGN § контракт game/mission](../DESIGN.md#контракт-game--mission)).

#### Inference — одна область, режим `mode`

Наследует из Config: `game`, `mission`, `save_state`.  
Общее (live + pool): `model` — enum `models/*.zip` (без `runs/`, `*.prev.zip`, `smoke_*`); дефолт `gen0.zip`.

**`mode: live`**

- `stochastic` — bool, default `true`.
- `max_steps` — int, default `8000`.
- `turbo` — bool, default `false`.
- `reward_profile` — enum из `routes.yaml → rewards`; default `default`.
- Действия: Запустить / Стоп.
- Запуск: preflight → `inference_local.sh --live` (или `run_inference.py --live --skip-preflight`).
- Инварианты: окно FCEUX + `fceux/operator/fceux.cfg`; без записи `logs/genN/`; цикл эпизодов до стоп.

**`mode: pool`** (сбор [пула поколения](../GLOSSARY.md#пул-поколения))

- `episodes` — int, default `5`.
- `stochastic` — bool, default `true`.
- `max_steps` — int, default `8000`.
- `wipe_gen_logs` — bool, default `false`.
- `reward_profile` — enum; default `default`.
- Действия: Собрать / Стоп.
- Собрать: preflight (опц. wipe) → `inference_local.sh` без `--live` (`--episodes N`).
- Инварианты: headless pool; пишет `logs/<model_version>/` (`attempts.jsonl`, `inference_inputs.jsonl`); без плейлиста / editorial.

**`mode: replay`** (проигрывание одного клипа)

- `input` — путь к `.fm2` (дефолт: первый `.fm2` в `logs/<model_version>/` по `model`, иначе пусто).
- `turbo` — bool, default `false`.
- `timeout` — float, default `120`.
- Действия: Запустить / Стоп.
- Запуск: preflight playback → `play_inference_fm2.py <input>`; окно FCEUX по умолчанию видно (без `--noicon`).

Взаимоисключение режимов — как `validate_inference_args` в `run_inference.py` (live не смешивать с pool-флагами). В UI показывать только опции активного `mode`.

#### Train

- Наследует из Config: `game`, `mission`, `save_state`.
- `train_mode` — `continue` | `scratch` | `from_ancestor` (вкладка **Train**).
- **Rollback** — отдельная вкладка: `model_out`, кнопка «Откатить» (`--rollback`, без learn).
- `model_out` — enum `models/*.zip`; дефолт `gen0.zip`.
- `model_in` — enum; только для `from_ancestor`.
- `timesteps` — int, default `500000`.
- `n_envs` — int, default `6` (как `train_local.sh`).
- `bc_epochs` — int, default `0`; `bc_demo` — обязателен при `bc_epochs > 0` (`reference/demos_for_bc/seg_*.npz`); пустое значение в UI не запускается (иначе BC подхватит все сегменты).
- `reward_profile` — enum из `routes.yaml → rewards`; default `default`.
- Логирование (прокси CLI, без нового логгера в ядре):
  - `progress_pct` — bool → инверсия `--no-progress-pct` (колонки `progress_pct` / `target_timesteps`); default `true`.
  - `save_every` — int → `--save-every` (промежуточные save в `models/runs/`); default `50000`.
  - `latest_model` — bool → `--latest-model`; default `true`.
  - `latest_every` — int → `--latest-every` (частота `genN.latest.zip`); default `5`.
  - `save_log` — bool, default `false`; tee stdout в `tmp/bench/YYYYMMDD_HHMMSS_{model}_{train_mode}_[bc_epochs_N]_{timesteps}.log` (сырые значения + sanitize); GUI — через `ProcessRunner`, превью команды — `shell_with_tee`.
  - Панель stdout в GUI: subprocess `train_local.sh` → скролл вывода (та же таблица SB3, что в терминале).
- Действия: Запустить / Стоп (вкладка **Train**); «Откатить» — вкладка **Rollback**.
- Запуск: `train_preflight` → `train_local.sh`; стоп — graceful interrupt (атомарный save `model_out` + sidecar). Перед `continue`/`scratch` на существующем zip — snapshot `genN.prev.zip`.
- Вне UI v1 (advanced): `--smoke`, `--dummy-vec`, PPO-гиперпараметры, `--allow-reduce-target`, `--task` JSON.

### План реализации клиента

**Стек:** Tkinter (встроен в Python на Windows, без новых зависимостей в `requirements.txt`). Не Qt/web/Electron — только формы, subprocess и панель лога.

**Раскладка кода**

| Модуль | Назначение |
| ------ | ---------- |
| `scripts/operator_launcher.py` | Фасад: `sys.path` → `operator_launcher.main()` |
| `src/operator_launcher/app.py` | `Tk` root, вкладки/блоки Config / Inference / Train |
| `src/operator_launcher/workspace.py` | Чтение/запись `config/workspace.yaml` (`game`, `mission`, `save_state`) |
| `src/operator_launcher/catalog.py` | Enum для UI: игры, миссии, save_state якоря, `models/*.zip`, reward profiles |
| `src/operator_launcher/runner.py` | Один subprocess; start/stop; pump stdout/stderr в GUI |
| `src/operator_launcher/commands.py` | Сбор argv для `train_local.sh`, `inference_local.sh`, `play_inference_fm2.py` |

Логика train/inference **не** в GUI — только argv и `repo_root()` из [`project_paths.py`](../../src/project_paths.py).

**Этапы (≈ одна сессия на этап)**

1. **Каркас + Config** — окно Tk, `workspace.yaml` load/save, combobox game/mission/save_state; кнопка «Применить».
2. **Catalog** — `list_games()`, `list_missions()`, `list_save_state_anchors()`, `list_model_zips()` из layout миссии; без `if game_id`.
3. **Runner** — `subprocess.Popen` из корня репо; поток читает pipe → `queue` → `Text`; env `PYTHONIOENCODING=utf-8`; один активный процесс (блокировать второй запуск).
4. **Inference** — переключатель `mode`; условные поля; live/pool → preflight + `run_inference`; replay → `play_inference_fm2.py` (один `.fm2`); стоп через terminate/SIGINT-эквивалент.
5. **Train** — `train_mode`, прокси флагов логирования, «Откатить»; общая панель stdout с Inference.
6. **Приёмка + SCRIPTS.md** — ручной прогон на m1; регистрация entry point.

**Стоп и безопасность**

- Train: предпочтительно отправить Ctrl+C в процесс (graceful save), затем при таймауте — kill.
- Inference live/pool: стоп = завершение subprocess (FCEUX закрывается с env).
- Перед запуском: проверка «процесс уже работает»; disable кнопок Запустить на активной вкладке.

**Расширение workspace**

```yaml
game: rushn_attack
mission: m1
save_state: save_states/cp_gameplay0.fc0
```

Лаунчер всегда передаёт `--game`, `--mission`, `--save-state` в дочерние скрипты явно (CLI > yaml для subprocess; yaml — дефолт оператора в GUI).

### Чеклист сессии

- [x] Этап 1–2: каркас Tk + Config + `catalog.py`
- [x] Этап 3: `runner.py` (subprocess, stdout-панель, один процесс)
- [x] Этап 4: Inference (live / pool / replay, без editorial)
- [x] Этап 5: Train + «Откатить»
- [x] Этап 6: SCRIPTS.md (регистрация); ручная приёмка m1 — оператору

### Критерий готовности (DoD)

- [x] Config сохраняется в `workspace.yaml`; train/inference без ручного `--game`/`--mission` берут тот же контекст
- [ ] Inference live / pool / replay запускаются из GUI и соответствуют утверждённым инвариантам (pool ≠ live флаги)
- [ ] Train: continue/scratch/from_ancestor/rollback; стоп сохраняет `model_out`; stdout виден в панели
- [x] Нет игро-специфики в ядре ради лаунчера; enum из layout плагина и manifest
- [x] Новый entry point зарегистрирован в SCRIPTS.md

### Не делать (антискоуп)

- Дублировать train/inference/preflight в GUI — только фасад subprocess
- `if game_id == …` и хардкод RnA/m1 в `src/`
- Content production / стриминг (вне фокуса проекта)
- Парсинг rollout-таблицы SB3 в графики; отдельный логгер в ядре train
- Smoke/benchmark артефакты в `games/…/models/` из лаунчера

### Заметки / гипотезы

- Inference live / pool / replay объединены в одну область с `mode` (меньше дублирования `model` / Config).
- GUI: **Tkinter** (см. [План реализации клиента](#план-реализации-клиента)); CustomTkinter — только если v1 визуально неудовлетворит.
- Расширение workspace полем `save_state` — скрипты получают `--save-state` от лаунчера; yaml — дефолт оператора.
