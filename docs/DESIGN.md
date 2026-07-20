# DESIGN — паттерны проектирования wait/

> **Конституция кода:** куда класть новую логику и какие паттерны обязательны.  
> Индекс: [README.md](README.md) · Задачи: [TASK_BLANK](tasks/TASK_BLANK.md) · ML: [ML_CONCEPT.md](ML_CONCEPT.md)

---

## Главный паттерн: Pluggable Core

**Ядро** (`src/`) — стабильный каркас. **Плагин** (`games/<game_id>/`) — игра и миссии.  
Третьего пути нет: общий механизм → ядро; игро-специфика → плагин.

```
┌─────────────────────────────────────────┐
│  CORE (src/)                            │
│  bridge · env · rewards · train         │
│  inference · achievements · utils       │
└──────────────┬──────────────────────────┘
               │ make_env(game_id)
               ▼
┌─────────────────────────────────────────┐
│  PLUGIN (games/<game_id>/)              │
│  game.yaml · env/ · missions/<m>/       │
└─────────────────────────────────────────┘
```

**Правило:** новая игра = новый каталог в `games/`, не копия `src/train/` или `src/stream/`.

---

## Структура репозитория

Единственный полный список каталогов и классов артефактов (git / локально / хост).

### Слои


| Слой | Каталог | Содержимое |
| ---- | ------- | ---------- |
| **Игры** | `games/<game_id>/` | ROM, миссии, эталон, модели, логи, env-пакет, `env_config.yaml` |
| **Код (общий)** | `src/`, `scripts/` | FCEUX bridge, `BaseNesEnv`, награды, train/inference |
| **Эмулятор** | `fceux/` | Portable FCEUX 2.6.6 win64 + Lua + профили |
| **Документация** | `docs/` | Концепция ядра + `GAME_*.md`; `ram_map.md` — в миссии |

**Правило:** меняется только при смене игры → `games/<game_id>/`. Каркас (`BaseNesEnv`, `CheckpointRewardWrapper`, `make_env`) → `src/`.

- Пути в YAML/JSON миссии — **относительно** `games/<game_id>/missions/<mission_id>/`.
- Как добавить игру — [ML_CONCEPT.md §10](ML_CONCEPT.md#10-структура-репозитория).

### В проекте vs окружение


| Класс | Смысл | Git |
| ----- | ----- | --- |
| **A — репозиторий** | Исходники, документация, конфиги, контракты | да |
| **B — локально в** `wait/` | Portable, ROM, ML-артефакты, venv, tmp | нет (`.gitignore`) |
| **C — окружение хоста** | ОС, Python, системные программы | вне репо |

#### A — в git

| Путь | Содержимое |
| ---- | ---------- |
| `docs/` | Концепция |
| `config/achievements.yaml` | Номинации achievements (текущая игра) |
| `src/` | Общий bridge, env, rewards, train, inference |
| `scripts/` | CLI |
| `fceux/lua/`, `fceux/profiles/`, `fceux/runtime.yaml`, `fceux/README.md` | Контракт эмулятора |
| `games/<game>/game.yaml`, `env_config.yaml`, `env/` | Плагин игры |
| `games/…/missions/…/config/`, `ram_map.md` | CP, rewards, heuristics (в git — контракты; данные эталона — часто B) |
| `requirements.txt`, `.gitignore` | Зависимости / исключения B |

#### B — в `wait/`, не в git

| Путь | Содержимое | Как появляется |
| ---- | ---------- | -------------- |
| `fceux/portable/` | FCEUX 2.6.6 win64 | распаковка ([fceux/README.md](../fceux/README.md)) |
| `games/<game>/rom/*.nes` | ROM | вручную (legal) |
| `games/…/reference/` | FM2, jsonl, scout, demos_for_bc | запись эталона |
| `games/…/config/` runtime | `ram_resolve.json`, `inference.*` | scout / build |
| `games/…/save_states/`, `models/`, `logs/`, `tasks/`; `reference/demos_for_bc/` | ML / эталон | train / inference / BC |
| `.venv/` | pip-пакеты | `requirements.txt` |
| `tmp/` | IPC FCEUX ↔ Python | runtime |

#### C — хост

| Компонент | Этап |
| --------- | ---- |
| Windows 10, Python 3.10/3.11, Git | A |
| pip в `.venv/` | A |
| NVIDIA + NVENC, OBS, Twitch, upload ≥5 Mbps | B (эфир) |

**Правило:** воспроизводимость ML — git (A) + `requirements.txt` / скрипты (B+C). ROM и models — копированием `games/`, не через git.

### Дерево

```
wait/
├── config/achievements.yaml
├── docs/                    # README (вход), ML, STREAMING, DESIGN, GAME_*
├── games/<game_id>/
│   ├── game.yaml
│   ├── env_config.yaml
│   ├── env/
│   ├── rom/
│   └── missions/<mission_id>/
│       ├── ram_map.md
│       ├── config/
│       ├── reference/           # FM2, jsonl, scout/, demos_for_bc/
│       ├── save_states/
│       ├── models/
│       ├── logs/
│       └── tasks/
├── src/
├── fceux/                   # portable + lua/profiles
├── scripts/
├── requirements.txt
├── .venv/
├── tmp/
└── .gitignore
```

`streaming/` (OBS) — этап B, класс A, когда появится. Пилот — [GAME_RUSHN_ATTACK.md](GAME_RUSHN_ATTACK.md).

### FCEUX: portable и режимы

Один бинарник — [FCEUX 2.6.6 win64](https://fceux.com/web/download.html) в `fceux/portable/`; контракт — `fceux/runtime.yaml`.

| Режим | Профиль | Процессов | Lua | Turbo | Окно |
| ----- | ------- | --------- | --- | ----- | ---- |
| Запись эталона | `profiles/record.yaml` | 1 | `record_logger.lua` | выкл | да |
| Обучение | `profiles/train.yaml` | 4–8 | `bridge.lua` | вкл | headless |
| Inference | `profiles/inference.yaml` | 1 | `bridge.lua` | вкл | headless (`--show-window`) |

Launcher: `runtime.yaml` + `profiles/<mode>.yaml` + `--game` / `--mission`. Override: `FCEUX_HOME`. Платформа: Windows 10; portable win64.

---

## Слоты паттернов

| Слот | Паттерн | Куда | Пример |
| ---- | ------- | ---- | ------ |
| Внешняя система | **Adapter** | `src/` | `FceuxBridge`, `fm2_export` |
| Создание env | **Abstract Factory** | `src/env/loader.py` + `games/.../env/` | `make_env()`, `build_vec_env()` |
| Награды, метрики на env | **Decorator** | `src/rewards/` | `CheckpointRewardWrapper` |
| Варианты правил | **Strategy** | YAML + тонкий evaluator | `routes.yaml`, `achievements.yaml` |
| Общий цикл env, hooks | **Template Method** | `BaseNesEnv` + override в плагине | `_death_occurred()` |
| CLI / smoke | **Facade** | `scripts/` | `smoke_bridge.py`, `run_inference` entry |
| Цепочка артефактов | **Pipeline** | `scripts/` → `src/` | scout → build → train → inference |

**Правило:** не знаете, куда положить код — определите слот из таблицы.

---

## Семь правил разработки

### 1. Плагин не импортирует train/inference

Плагин экспортирует `make_env()` и конфиги. Train и inference идут через фабрику (`env.loader.make_env`).  
Ядро не зависит от конкретной игры.

### 2. Игровая логика — Strategy в YAML

CP, heuristics, профили наград — в `games/.../config/` (миссия) и `games/<game>/` (игра).  
В `src/` — только интерпретатор (`trigger_matches`, `mission_complete_heuristic`, `playthrough_build`, загрузчики YAML).

**Плохо:** константы комнат, CP-имена или эвристики сборки эталона в `src/`.  
**Хорошо:** `routes.yaml` (runtime CP); `etalon_build.yaml` + ключ в `game.yaml` (сборка эталона из FM2).

### Именование в коде

Имена в `src/`, `scripts/`, `tests/` и артефактах плагина — **предметная область**, не roadmap и не номера «фаз» планирования.

| Плохо | Хорошо |
| ----- | ------ |
| `phase0_config`, `load_phase0_*` | `etalon_build_config`, `load_etalon_build_config` |
| `phase0.yaml` в `game.yaml` | `etalon_build.yaml`, `etalon_build_config` |
| `data`, `info`, `handler`, `util` без смысла | `transition_rooms`, `checkpoint_heuristics`, `human_playthrough` |

Ориентиры: PEP 8, PEP 20 («Explicit is better than implicit»), выразительные имена (Clean Code).  
Функция — действие или результат; переменная — роль или значение; класс — сущность.  
Ясность важнее краткости. Roadmap ML («Phase 0», «Phase 1»…) — только в `ML_CONCEPT.md` / `README.md`, **не** в идентификаторах кода.

**Плохо:** `if game_id == "rushn_attack": ...` в ядре.  
**Хорошо:** правило в YAML плагина; ядро читает и интерпретирует.

### 3. Награды — только Decorator

`BaseNesEnv.step()` возвращает `reward=0.0`. Награда — в `CheckpointRewardWrapper`.  
Новая схема наград = новый wrapper, не правка `step()`.

### 4. Внешние процессы — только Adapter

FCEUX, FM2, OBS (этап B) — за адаптером с узким API.  
Ядро не размазывает IPC-детали (файлы, Lua) по train/inference.

### 5. `scripts/` — Facade, без бизнес-логики

Скрипт: argv → вызов `src/`. Логика в модулях `src/`, не в 200 строках CLI.

### 6. Расширение игры — Template Method

Общий цикл `reset → step → obs` в `BaseNesEnv`. Плагин переопределяет hooks при необходимости; action set — через `env_config.yaml`.

### 7. Корень причины, не следствие

Порядок обязателен: **воспроизвести → локализовать причину → исправить причину → проверить, что симптом исчез**.  
Обход следствия (маска, эвристика «на глаз», пост-обработка вместо исправления источника, «временно заглушить») — **нарушение рабочего процесса**, даже если снаружи «стало лучше» или тесты зелёные.

**Плохо:** подогнать артефакт / порог / костыль под наблюдаемый симптом и считать задачу закрытой.  
**Хорошо:** назвать слой и механизм сбоя, устранить его в месте возникновения, закрепить проверкой на причину (не только на симптом).  
Experiment-ветки — для проверки гипотез; в main и в постоянные доки/скрипты попадает только фикс корня, не замена ему.

---

## Decision tree: куда класть код

```
Новый код?
│
├─ Только для одной игры / миссии?
│   ├─ Правила, CP, heuristics (runtime) → games/.../missions/.../config/*.yaml (Strategy)
│   ├─ Heuristics сборки эталона → games/<game>/etalon_build.yaml
│   ├─ Действия, lives, env-параметры → games/.../env_config.yaml
│   └─ Фабрика env, override hooks → games/<game>/env/__init__.py
│
├─ Общий для всех игр?
│   ├─ Новый внешний процесс / протокол → src/*_bridge.py (Adapter)
│   ├─ Обвязка поведения env → src/rewards/ или wrapper (Decorator)
│   ├─ Общий алгоритм env → src/env/base_nes_env.py (Template Method)
│   └─ Train / inference / export → src/train/, src/stream/, src/
│
└─ Точка входа / smoke / benchmark → scripts/ (Facade)
```

---

## Антипаттерны

| Антипаттерн | Почему плохо | Вместо |
| ----------- | ------------ | ------ |
| `if game_id` в `src/` | Ядро раздувается с каждой игрой | YAML Strategy или hook в плагине |
| Игровые room/CP-константы в `src/` | Нарушает Pluggable Core | `etalon_build.yaml` / `routes.yaml` в плагине |
| Имена `phaseN_*`, `phaseN.yaml` в коде | Путает roadmap и runtime | доменные имена (`etalon_build`, `playthrough`, …) |
| Награды в `BaseNesEnv.step` | Нельзя менять профиль без форка env | `CheckpointRewardWrapper` |
| Бизнес-логика в `scripts/` | Дубли, нет переиспользования | `src/` + тонкий Facade |
| Копия train под игру | Два контура обучения | Один `train_ppo.py` + `make_env` |
| Новый конфиг-модуль на 3 константы | Шум, лишние импорты | Константа рядом с владельцем (см. archive [3.3](tasks/archive/TASK_FIRST_CAMPAIGN.md#33-inference-без-legacy-replay--убрать-inference_configpy)) |
| Smoke через `train_ppo` + `smoke_*` в models | Засоряет `games/` | `smoke_*.py` / `run_smoke.py`; карантин `tmp/smoke/` |
| Лечение следствия вместо причины | Ложный «успех», долг, регресс | [§7](#7-корень-причины-не-следствие): dig root cause; experiment ≠ merge |

---

## Стек внешних фреймворков

Не заменяем — строим плагины поверх:

| Фреймворк | Роль |
| --------- | ---- |
| **Gymnasium** | контракт `Env` |
| **Stable-Baselines3** | PPO, `VecEnv`, checkpoints |
| **PyTorch** | BC, inference |
| **FCEUX + Lua** | runtime эмулятора (Adapter в `FceuxBridge`) |

---

## Для AI-сессий

При объёмной работе — [TASK_BLANK](tasks/TASK_BLANK.md) (open в `docs/tasks/`, done → `archive/`). Архив первой кампании: [TASK_FIRST_CAMPAIGN](tasks/archive/TASK_FIRST_CAMPAIGN.md) (не подключать без нужды).

1. Определить слот (ядро / плагин / adapter / decorator).
2. Не нарушать семь правил выше (в т.ч. [§7](#7-корень-причины-не-следствие): не закрывать симптом компромиссом).
3. Smoke-проверка после изменений bridge/env — **`scripts/run_smoke.py`** (см. [SCRIPTS.md](SCRIPTS.md)).
4. CLI: новый / удалённый / изменённый скрипт или флаги — [алгоритм регистрации](#регистрация-скриптов-в-scriptsmd) в той же сессии.
5. В конце сессии — [гигиена артефактов](#гигиена-артефактов) (обязательно).

---

<a id="регистрация-скриптов-в-scriptsmd"></a>

## Регистрация скриптов в SCRIPTS.md

Цель: [SCRIPTS.md](SCRIPTS.md) остаётся **прозрачным каталогом**, а не журналом проекта.

### Когда трогать

| Событие | Действие |
| ------- | -------- |
| Новый постоянный CLI в `scripts/` или entry point (`train_ppo`, `run_inference`) | зарегистрировать |
| Удалён скрипт | вычеркнуть из всех трёх мест |
| Изменились флаги / дефолты / вход·выход | обновить **только карточку** |
| Одноразовый отладочный скрипт | **не** регистрировать — удалить в конце сессии |
| Замеры, контракты данных, pytest, журнал кампаний | **не** в SCRIPTS → [MEASUREMENTS](MEASUREMENTS.md) / [ML §8](ML_CONCEPT.md#8-форматы-данных) / [tasks/archive](tasks/archive/) |

### Алгоритм (add)

1. **Нужен ли постоянный entry point?** Если нет — не добавлять файл в `scripts/`, либо удалить до конца сессии.
2. **Карта задач** — одна строка «Хочу… → скрипт», только если это типовой сценарий оператора. Редкие/внутренние утилиты — только индекс + карточка.
3. **Индекс** — одна строка: путь | одно предложение.
4. **Карточка** по шаблону ниже. Без истории, baseline-таблиц, номеров этапов старых кампаний.
5. Сверить флаги с `argparse` / `-h`: в карточке — обязательные, частые, неочевидные. Не дублировать полный `-h`.
6. Общие `--game` / `--mission` не раздувать, если дефолты стандартные.

### Алгоритм (change / remove)

1. Найти карточку по имени файла.
2. **Change:** поправить флаги и вход/выход; устаревшие флаги удалить сразу.
3. **Remove:** убрать строку из карты задач (если была), из индекса и всю карточку. Починить битые ссылки из других docs на якорь карточки.

### Шаблон карточки (не раздувать)

```markdown
### `name.py`

Одно–два предложения: зачем.

\`\`\`bash
# одна каноническая команда (+ опц. вторая для отладки)
\`\`\`

| Флаг | Описание |
| ---- | -------- |
| … | … |
```

Допустимо кратко: вход → выход. Запрещено в карточке: таблицы ms/FPS, «этап 1.x», длинные runbook, дубли ML/STREAMING.

### Антипаттерны (снова «тёмный лес»)

- Писать в SCRIPTS результаты бенчей или выводы расследований (TASK/archive).
- Дублировать одну и ту же прозу в карте + индексе + карточке.
- Регистрировать скрипты «на всякий случай» без постоянного CLI.
- Оставлять флаги, которых уже нет в коде.
- Заводить отдельные `ISSUE_*` — гипотезы только внутри TASK.

---

## Гигиена артефактов

Smoke и benchmark **не засоряют** `games/`. Временный вывод — только в `tmp/` (gitignored).

### Политика

| Тип проверки | Вывод | Запрещено |
| ------------ | ----- | --------- |
| Smoke | stdout; IPC в `tmp/bridge/` | `games/.../models/smoke_*`, одноразовые `scripts/` |
| Benchmark | stdout; `tmp/bench/<session>/` | то же |
| Train | `games/.../models/` | запуск `train_ppo` «для smoke» с именами `smoke_*` |
| Inference | `games/.../logs/` | только явный inference |

**Smoke-скрипты:** `run_smoke.py` (фасад) → `smoke_bridge.py`, `smoke_env.py`, `test_parallel_env.py` — не `train_ppo.py`.

### API (`src/project_paths.py`)

| Функция | Назначение |
| ------- | ---------- |
| `artifact_quarantine_dir(kind, session)` | `tmp/smoke/` или `tmp/bench/` + session |
| `artifact_session(kind, session)` | контекст с cleanup в `finally` |
| `cleanup_artifact_quarantine(kind, session)` | удалить tmp-карантин |
| `cleanup_mission_smoke_models(mission)` | убрать ошибочные `smoke_*` из models |
| `find_stray_smoke_artifacts(mission)` | список забытых `smoke_*` в games |

### Чеклист конца сессии (агент / разработчик)

- [ ] `cleanup_artifact_quarantine("smoke")` / `("bench")` если создавались сессии
- [ ] `cleanup_mission_smoke_models(mission_dir(...))` или вручную удалить `smoke_*`
- [ ] Нет новых одноразовых скриптов в `scripts/`
- [ ] `find_stray_smoke_artifacts` → пусто
- [ ] [SCRIPTS.md](SCRIPTS.md) синхронизирован по [алгоритму регистрации](#регистрация-скриптов-в-scriptsmd)

Правило для агента: [.cursor/rules/artifact-hygiene.mdc](../.cursor/rules/artifact-hygiene.mdc).

---

## Что не является главным паттерном

MVC, Repository, полный DDD, Event Sourcing, microservices — не подходят как основа для этого репозитория (CLI + эмулятор + файловые артефакты, solo).
