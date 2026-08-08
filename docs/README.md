# README — AI NES Learning

> **Единая точка входа** для разработки и AI-агентов.  
> **Цель:** платформа для обучения AI прохождению игр NES/Famicom.  
> **Пилот:** [GAME_RUSHN_ATTACK.md](GAME_RUSHN_ATTACK.md) (Rush'n Attack M1).  
> **Направление форка:** curiosity-driven learning — детали и смена thesis обучения живут в форке; этот репозиторий готовит каркас без смены контракта платформы.

Два слоя документации (не смешивать):

| Слой | Смысл | Документы |
| ---- | ----- | --------- |
| **A — платформа** | Контракт кода и операторский каркас; наследуется форком | [DESIGN](DESIGN.md), [SCRIPTS](SCRIPTS.md), [GLOSSARY](GLOSSARY.md) (env/bridge/пути), fceux, правила агента |
| **B — baseline ML** | Текущий путь: extrinsic PPO, CP-награды, эталон, дообучение; **не** DoD curiosity-форка | [ML_CONCEPT](ML_CONCEPT.md), [PROTOCOL](PROTOCOL_MISSION_REFERENCE.md), GAME §награды/приёмка, [TRAIN_ANALYSIS](TRAIN_ANALYSIS.md) |

---

## Документы

### A — платформа (контракт)

| Документ | Фокус |
| -------- | ----- |
| **[DESIGN.md](DESIGN.md)** | Pluggable Core, слоты, дерево репо / git A–B–C, гигиена · [регистрация скриптов](DESIGN.md#регистрация-скриптов-в-scriptsmd) |
| **[SCRIPTS.md](SCRIPTS.md)** | Каталог CLI: назначение и флаги entry point'ов (без замеров / журналов) |
| **[GLOSSARY.md](GLOSSARY.md)** | Единый словарь (алфавитный порядок) |
| **[tasks/TASK_BLANK.md](tasks/TASK_BLANK.md)** | Каркас задач: open в `tasks/`, done → `tasks/archive/` (без `ISSUE_*`) |

Правила AI-агента (Cursor): [pluggable-core](../.cursor/rules/pluggable-core.mdc) · [agent-communication](../.cursor/rules/agent-communication.mdc) · [artifact-hygiene](../.cursor/rules/artifact-hygiene.mdc).

### B — baseline ML (до форка)

| Документ | Фокус |
| -------- | ----- |
| **[ML_CONCEPT.md](ML_CONCEPT.md)** | Baseline: PPO, награды CP, эталон, train pipeline · [скрипты](SCRIPTS.md) |
| **[PROTOCOL_MISSION_REFERENCE.md](PROTOCOL_MISSION_REFERENCE.md)** | Runbook эталона миссии для baseline (не конституция форка) |
| **[GAME_RUSHN_ATTACK.md](GAME_RUSHN_ATTACK.md)** | Пилот: env/actions полезны; награды/приёмка — gate baseline |
| **[TRAIN_ANALYSIS.md](TRAIN_ANALYSIS.md)** | Чтение консоли текущего `train_ppo` (SB3); не про intrinsic-метрики |

**Open (не стратегический шаг форка):** [TASK_OPERATOR_LAUNCHER](tasks/TASK_OPERATOR_LAUNCHER.md) — операторский GUI.

**Архив:** `docs/tasks/archive/` — история baseline; **не** подключать в промпт при работе над форком.

---

<a id="порядок-разработки"></a>

## Порядок разработки

| Этап | Фокус | Документ | Статус |
| ---- | ----- | -------- | ------ |
| **Baseline ML** | FCEUX bridge, env, train, локальный inference, дообучение | [ML_CONCEPT.md §11](ML_CONCEPT.md#11-roadmap-ml-фазы) | текущий путь в этом репо |
| **Форк** | Curiosity-driven learning | отдельный репозиторий / ветка форка | подготовка: слой A без ломки контракта |

**Приёмка baseline:** [ML_CONCEPT.md §12](ML_CONCEPT.md#12-критерии-приёмки-ml) + [GAME_RUSHN_ATTACK.md §5](GAME_RUSHN_ATTACK.md#5-приёмка-пилота) — gate *baseline-пайплайна*, не обязательный DoD curiosity-форка.

На текущем этапе: `run_inference` и `attempts.jsonl` — [пул поколения](GLOSSARY.md#пул-поколения); `--live` — операторский просмотр в окне FCEUX (без записи пула).

<a id="состав-проекта"></a>

## Состав проекта (кратко)

| Класс | Примеры | Где |
| ----- | ------- | --- |
| **Код и конфиги** | `src/`, `scripts/`, `fceux/lua/`, `game.yaml`, `routes.yaml` | `wait/`, **в git** |
| **Portable в проекте** | FCEUX 2.6.6 (`fceux/portable/`) | `wait/`, **не в git** — распаковка вручную ([fceux/README.md](../fceux/README.md)) |
| **Данные и артефакты** | ROM, models (`genN`), demos, save states, логи | `games/…`, **не в git** |
| **Python-стек** | PyTorch, SB3, gymnasium… | `.venv/` в `wait/`, **не в git**; ставится из `requirements.txt` |
| **Окружение хоста** | Windows 10, Python 3.11, Git, драйвер NVIDIA (опц.) | системная установка |

Полная матрица артефактов — [DESIGN.md § Структура](DESIGN.md#структура-репозитория). Скрипты — [SCRIPTS.md](SCRIPTS.md).

**Агенты:**  
- CLI add·remove·change — [DESIGN § Регистрация скриптов](DESIGN.md#регистрация-скриптов-в-scriptsmd).  
- Объёмная работа — [TASK_BLANK](tasks/TASK_BLANK.md); archive не подключать без нужды.

## Железо (хост, 2026-07-05)

| Ресурс | Состав | ML |
| ------ | ----- | -- |
| CPU | Intel **i7-3770** @ 3.40 GHz (4C/8T) | PPO на CPU; live/pool inference |
| RAM | 2×8 GB Kingston DDR3-1600 (16 GB) | 4–8 parallel env |
| GPU | **GTX 650** 1 GB | PyTorch CPU-only |
| SSD | Kingston SA400S37 480 GB | модели, логи, demos |
| МП | MSI **H61M-P20/W8** (MS-7788) | — |
| ОС | Windows 10 Pro, build **19045** | Платформа проекта |

БП заменён при апгрейде (2026-07); модель/мощность из OS не читаются.  
Апгрейд: i3-3210 → **i7-3770**.

Правила нагрузки: [ML_CONCEPT.md §2](ML_CONCEPT.md#2-инфраструктура-обучения).

---

## Следующий шаг

**Baseline:** Python `.venv` (`scripts/setup_venv.ps1`), эталон пилота по [PROTOCOL](PROTOCOL_MISSION_REFERENCE.md) / [GAME](GAME_RUSHN_ATTACK.md).  
Окружение: `scripts/setup_all.ps1` · проверка: `python scripts/verify_env.py`.  
Phases baseline — [ML_CONCEPT.md §11](ML_CONCEPT.md#11-roadmap-ml-фазы).  

**Форк:** не разворачивать curiosity-концепт в этом репо до отдельной линии; слой A (DESIGN / SCRIPTS / bridge) уже готов к наследованию.
