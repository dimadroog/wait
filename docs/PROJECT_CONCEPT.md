# PROJECT_CONCEPT — AI NES Learning Stream

> **Единая точка входа** для разработки и AI-агентов.  
> Статус: утверждённая концепция MVP. Код — Phase 0.  
> **Игра MVP:** Rush'n Attack, M1.  
> **Приоритет:** ML-стек (этап A) → стриминговое ПО (этап B, после gate).

---

## Документы

| Документ | Фокус |
| -------- | ----- |
| **[DESIGN.md](DESIGN.md)** | Паттерны проектирования: Pluggable Core, слоты, decision tree, антипаттерны |
| **[STREAMING_CONCEPT.md](STREAMING_CONCEPT.md)** | Twitch, OBS, сюжет эпизода, метрики для зрителя, сезоны · [GLOSSARY.md](GLOSSARY.md) |
| **[ML_CONCEPT.md](ML_CONCEPT.md)** | PPO/BC, среда, награды, эталон, данные, train pipeline · [GLOSSARY.md](GLOSSARY.md) · [скрипты](SCRIPTS.md) |
| **[SCRIPTS.md](SCRIPTS.md)** | Консольные скрипты: setup, RAM scout, train (план) |

Термины — [GLOSSARY.md](GLOSSARY.md) (единый словарь, алфавитный порядок).

---

<a id="порядок-разработки"></a>

## Порядок разработки

| Этап | Фокус | Документ | Статус |
| ---- | ----- | -------- | ------ |
| **A — ML** | FCEUX bridge, env, train, локальный inference, дообучение | [ML_CONCEPT.md §11](ML_CONCEPT.md#11-roadmap-ml-фазы) | **текущий** |
| **B — Стрим** | OBS, Twitch, overlay, тестовый эфир | [STREAMING_CONCEPT.md §10–11](STREAMING_CONCEPT.md#10-roadmap) | после gate |

**Gate (A → B):** все пункты [ML_CONCEPT.md §12](ML_CONCEPT.md#12-критерии-приёмки-ml) — в т.ч. стабильно CP2–3 и цикл дообучения.

До gate: **не** ставить OBS, **не** настраивать Twitch, **не** готовить overlay.  
inference и `attempts.jsonl` на этапе A — локальная отладка модели без эфира.

[STREAMING_CONCEPT.md](STREAMING_CONCEPT.md) — спецификация этапа B; реализация отложена.

<a id="состав-проекта"></a>

## Состав проекта (кратко)

| Класс | Примеры | Где |
| ----- | ------- | --- |
| **Код и конфиги** | `src/`, `scripts/`, `fceux/lua/`, `game.yaml`, `routes.yaml` | `wait/`, **в git** |
| **Portable в проекте** | FCEUX 2.6.6 (`fceux/portable/`) | `wait/`, **не в git** — распаковка вручную ([fceux/README.md](../fceux/README.md)) |
| **Данные и артефакты** | ROM, checkpoints, demos, save states, логи | `games/…`, **не в git** |
| **Python-стек** | PyTorch, SB3, gymnasium… | `.venv/` в `wait/`, **не в git**; ставится из `requirements.txt` |
| **Окружение хоста** | Windows 10, Python 3.11, Git, драйвер NVIDIA | системная установка |
| **Стрим (этап B)** | OBS, Twitch | системная установка; конфиги сцен — позже в `streaming/` |

Полная матрица — [ML_CONCEPT.md §10](ML_CONCEPT.md#в-проекте-vs-окружение). Скрипты — [SCRIPTS.md](SCRIPTS.md).

## Железо (хост, 2026-07-05)

| Ресурс | Состав | Стрим | ML |
| ------ | ------ | ----- | -- |
| CPU | Intel **i7-3770** @ 3.40 GHz (4C/8T) | Inference, FCEUX | PPO на CPU |
| RAM | 2×8 GB Kingston DDR3-1600 (16 GB) | — | 4–8 parallel env |
| GPU | **GTX 650** 1 GB | OBS NVENC | PyTorch CPU-only |
| SSD | Kingston SA400S37 480 GB | — | модели, логи, demos |
| МП | MSI **H61M-P20/W8** (MS-7788) | — | — |
| ОС | Windows 10 Pro, build **19045** | MVP-платформа | MVP-платформа |
| Upload | ≥5 Mbps | Twitch | — |

БП заменён при апгрейде (2026-07); модель/мощность из OS не читаются.  
Апгрейд: i3-3210 → **i7-3770**.

Правила нагрузки: [STREAMING_CONCEPT.md §4](STREAMING_CONCEPT.md#4-инфраструктура-эфира) (эфир) · [ML_CONCEPT.md §2](ML_CONCEPT.md#2-инфраструктура-обучения) (обучение).

---

## Следующий шаг

**Этап A — ML Phase 0:** Python `.venv` (`scripts/setup_venv.ps1`), RAM-разведка, запись эталона M1.  
Окружение: `scripts/setup_all.ps1` · проверка: `python scripts/verify_env.py`.  
Далее — ML Phases 1–4 по [ML_CONCEPT.md §11](ML_CONCEPT.md#11-roadmap-ml-фазы).
