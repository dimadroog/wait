# TASK_SCRIPTS_AUDIT — аудит публичного CLI + гигиена Pluggable Core

**Статус:** done  
**Закрыто:** 2026-07-27 — workspace CLI, Pluggable Core hygiene, thin facades; G1–G13; merge `3f91600` в `main`.  
**Приоритет:** high  
**Ветка:** `task/scripts-audit`  
**Зависит от:** безопасный контракт train `model-in`/`model-out` (done на `main`: continue / from_ancestor / scratch)  
**Файлы:** `docs/SCRIPTS.md`, `docs/DESIGN.md`, `docs/GLOSSARY.md`, `.cursor/rules/pluggable-core.mdc`, `.cursor/rules/` (новые mdc при необходимости), `config/workspace.yaml` (новый), `src/project_paths.py` (или тонкий `cli_defaults`), `scripts/*`, `src/train/*`, `src/stream/*`, `src/achievements/*`, `src/fm2_playback.py`, `src/playthrough_build.py`, `games/<id>/achievements.yaml` (бывш. корневой `config/achievements.yaml`)  
**Контекст в чат:** этот файл + [SCRIPTS.md](../../SCRIPTS.md) + [DESIGN.md](../../DESIGN.md) + [pluggable-core.mdc](../../../.cursor/rules/pluggable-core.mdc)

Каркас: [TASK_BLANK.md](../TASK_BLANK.md)

### Цель

1. Убрать CLI-ловушки того же класса, что бывший `--resume` / молчаливый wipe: опасные дефолты, silent override, dual paths shell↔Python, docs-only флаги.  
2. Ввести **один** источник дефолтов игра/миссия (`config/workspace.yaml`); убрать id плагина из argparse ядра; выровнять scout и прочие скрипты (без cwd-как-контекста).  
3. Закрыть **серые зоны Pluggable Core**, куда агент пролезает без `if game_id`: словарь фаз пилота в train, PPU-эвристики, achievements вне `games/`, толстые `scripts/`.  
4. Усилить [pluggable-core.mdc](../../../.cursor/rules/pluggable-core.mdc) и [DESIGN.md](../../DESIGN.md); при необходимости выделить отдельные alwaysApply/globs mdc.

Принцип: скрипт либо отказывается, либо делает ожидаемо; ядро не «знает» Rush'n Attack даже через удобный default.

---

### Контракт резолва game / mission (зафиксировано)

**Один источник дефолтов — workspace-конфиг.** Не гибрид «cwd + yaml + хардкод».

```text
CLI --game / --mission (если заданы) — побеждают
  → иначе поля из config/workspace.yaml
    → иначе SystemExit: укажите флаги или заполните workspace
```

- В `src/**` argparse: `default=None` для game/mission; заполнение только через общий хелпер.  
- Явные флаги — осознанный override оператора.  
- **Антискоуп:** угадывание по `Path.cwd()` / walk-up к `games/…/missions/…`.  
- Scout: scope по пути FM2 + флаги/workspace; технический `cwd=` subprocess FCEUX ≠ выбор плагина.

Статья в [GLOSSARY](../../GLOSSARY.md) (при реализации): «конфиг рабочей области» — `config/workspace.yaml`; не путать с плагином `games/<id>/` и с `fceux/runtime.yaml`.

---

### Предметно: что переделать и почему

#### A. Контекст игра/миссия (pilot defaults)

| Что | Почему | Куда |
| --- | --- | --- |
| `default="rushn_attack"` / `"m1"` в `src/train/train_ppo.py`, `run_inference`, `fm2_export`, `playlist`, `broadcast_board`, `inference_preflight`, … | Ядро «знает» пилот; артефакты легко уезжают не в ту миссию | Workspace + хелпер; `default=None` |
| Те же defaults во всех `scripts/*.py`, `inference_local.sh` (`GAME=…`) | Dual canon; shell ≠ Python | Passthrough; резолв только в Python |
| `stress_parallel_reset` / `bench_parallel_step` без argparse, зашиты RnA/m1 | Нельзя сменить игру без правки кода | CLI + workspace или удалить/redirect на gate |
| `run_smoke` cleanup всегда `mission_dir("rushn_attack","m1")` | Жёсткий пилот в фасаде | Workspace / явный `--game`/`--mission` |
| `smoke_bridge` path к `clear.fm2` RnA | То же | Флаг / workspace |

#### B. CLI-ловушки артефактов

| Что | Почему | Куда |
| --- | --- | --- |
| `build_playthrough` удаляет все `save_states/*.fc0` | Молчаливый wipe чужих states | Только слоты плана или `--replace-states` |
| Stub demos поверх `record_demos` | Молчаливая порча BC | Не трогать non-stub без force |
| `inference_local`: wipe + `--skip-preflight` | Флаг «съеден», wipe не выполняется | Error на комбинацию или гарантированный wipe |
| `apply_task_defaults` перебивает CLI | Silent override (класс resume-trap) | CLI > task или exit при конфликте; deprecate `checkpoint_*` |
| Continue: CLI timesteps < sidecar | Оператор думает «укоротил», цель не падает | Explicit reduce или exit |
| `--model` vs `--model-version` расходятся | Пишет/чистит чужой `logs/genN/` | Exit при разном stem |
| `ram_scout` mission переписывает resolve | Ручные якоря затираются | Явный `--write-ram-map` |

#### C. Pluggable Core — словарь/эвристики пилота в ядре

| Что | Почему | Куда |
| --- | --- | --- |
| `phase_aware_ppo` / gate в `train_ppo`: литералы `title`/`intro`/`gameplay`, isolation | Не `if game_id`, но схема RnA в train-ядре; другая игра ломает gate | Контракт в `env_config` / policy_heads YAML плагина (запрещённые пары phase↔head, required phases); ядро только читает |
| `multi_head_policy` default `gameplay_head="gameplay"` | Имя головы пилота | Из манифеста голов плагина |
| `inference_states` / `playthrough_build`: ключ `"gameplay"`, fallback `cp_gameplay0` | Конвенция пилота как hard path | Только из `head_save_states` / манифеста; без магического имени в ядре или документированный нейтральный слот |
| `fm2_playback.ppu_screenshot_heuristic` | Пороги title/gameplay в коде | YAML/hook плагина или явная пометка probe + вынос |
| `achievements/playlist` ветки slug `episode_reward` / `fastest_death` | Номинации пилота в ядре | Плагин или data-driven sort key из YAML |
| `config/achievements.yaml` (+ `0x08`) вне `games/` | Игровые правила обходят плагин | `games/<id>/…` (или путь из game.yaml); ядро грузит через плагин |
| Толстые `scripts/` (`segment_playthrough`, куски playback/scout/bench) | Нарушение «scripts = фасад» | Логика → `src/`; CLI тонкий |

Train model-io (continue / from_ancestor / scratch) — **уже done**, не повторять.

---

### Гейты (обязательная приёмка)

Автоматические (pytest / CI-friendly, без FCEUX где возможно):

- [x] **G1 — нет pilot id в argparse src:** `rg 'default=["\']rushn_attack["\']|default=["\']m1["\']' src/` → пусто (после миграции на workspace).  
- [x] **G2 — резолв:** unit на хелпер: CLI > workspace > SystemExit; cwd не влияет (менять cwd в тесте).  
- [x] **G3 — model stem conflict:** unit: разные `--model` / `--model-version` → exit.  
- [x] **G4 — task vs CLI:** unit/хелпер: CLI wins (task только незаданные в argv поля); `checkpoint_*` deprecated.  
- [x] **G5 — wipe demos/states:** unit: non-stub npz и «лишний» `.fc0` не удаляются без явного replace/force.  
- [x] **G6 — phase vocabulary:** unit: isolation/required phases читаются из синтетического YAML плагина; в `src/train` нет захардкоженных кортежей `("title","intro")` как единственного правила (или они помечены deprecated и покрыты тестом «из YAML»).  
- [x] **G7 — achievements path:** загрузка конфига номинаций идёт из-под `games/<id>/` (или путь из game.yaml); unit с tmp plugin tree.  
- [x] **G8 — facade smell (мягкий):** список «толстых» scripts в заметках; для каждого — либо перенос в `src/`, либо явная отсрочка в антискоупе с датой.  
  - План: § «G8 — план переноса…» (2026-07-27). Волны A–C сделаны; bench/stress отсрочены до **2026-09-30**.

Ручные / операторские:

- [x] **G9:** команда train/inference **без** `--game`/`--mission` при валидном workspace пишет только в указанную миссию; при отсутствии workspace — отказ, не RnA.  
  - 2026-07-27: `resolve_game_mission(None,None)` → `rushn_attack/m1` из workspace; cwd не влияет (`test_workspace_resolve`); пустой workspace → `SystemExit`.  
- [x] **G10:** `docs/SCRIPTS.md` + DESIGN/GLOSSARY синхронизированы; `rg 'force-promote|--no-resume' docs/SCRIPTS.md docs/MEASUREMENTS.md` — нет живых ложных флагов.  
  - Удалён ложный `--force-promote` у `train_fps_round_prep`; дефолты game/mission → workspace; MEASUREMENTS: resume/`checkpoint_out` → continue `model-out`.  
- [x] **G11:** `pytest` затронутых тестов; mission `models/genN.zip` не меняется.  
  - 2026-07-27: **64 passed** (workspace, traps, fm2 resolve, phase_heads, achievements, ram_scout, fm2 helpers, playlist/editorial); `git status` без изменений `models/gen*.zip`.

Регрессия Pluggable Core (документировать в DESIGN, гонять в CI по возможности):

- [x] **G12:** `rg 'if game_id\s*==' src/` → пусто.  
- [x] **G13:** нет новых room/pose-литералов RnA в `src/` (выборочный review + запрет в mdc).  
  - 2026-07-27: `0x08` нет в `src/` (номинация в плагине); поле `death_room` / fallback `cp_gameplay0` — общие механизмы (серая зона из таблицы C, не новый литерал комнаты). Запрет в `pluggable-core.mdc` + DESIGN.
---

### Усиление правил для агента (DESIGN + mdc)

Сделать в этой же задаче (или первым чеклистом до большого кода):

#### 1. Обновить `.cursor/rules/pluggable-core.mdc`

Добавить явные запреты (сейчас ловится только `if game_id` и «комнаты/CP»):

- Запрет **строковых дефолтов id игры/миссии** в `src/**` (`default="rushn_attack"` и аналоги). Дефолт — только workspace / обязательный CLI.  
- Запрет **словаря фаз/голов конкретной игры** в ядре (`"title"|"intro"|"gameplay"` как hard isolation) — только интерпретация YAML/hooks плагина.  
- Запрет **игровых порогов PPU/RAM** (эвристики title, room id) в `src/` вне чтения конфига плагина.  
- Запрет класть **правила номинаций / routes-подобные числа** в корневой `config/`, если они про одну игру — путь `games/<id>/`.  
- Напомнить: отсутствие `if game_id` **не** означает чистоту ядра.

#### 2. Обновить `docs/DESIGN.md`

- Секция Pluggable Core / anti-patterns: строки про pilot argparse defaults, phase vocabulary в train, achievements вне плагина, cwd-как-контекст.  
- Контракт workspace (ссылка на GLOSSARY).  
- Decision tree: «куда класть дефолт игры» → workspace, не `src/`.

#### 3. Новые mdc (если pluggable-core раздуется)

Выделить **только если** объём запретов мешает читаемости alwaysApply:

| Правило | Когда | Содержание |
| ------- | ----- | ---------- |
| `pluggable-core.mdc` | alwaysApply | Конституция + расширенные запреты выше (предпочтительно оставить одним файлом) |
| `cli-workspace.mdc` (опц.) | globs: `scripts/**`, `src/train/**`, `src/stream/**` | Резолв game/mission; запрет cwd-контекста; workspace; SCRIPTS registration |
| `artifact-hygiene.mdc` | уже есть | Не дублировать; только ссылка из TASK |

**Решение по умолчанию:** сначала расширить существующий `pluggable-core.mdc` + DESIGN; отдельный `cli-workspace.mdc` — только если после правок alwaysApply станет шумным.

---

### Чеклист сессии

- [x] Усилить `pluggable-core.mdc` + DESIGN (+ GLOSSARY workspace); решить: нужен ли отдельный `cli-workspace.mdc`
  - **Решение:** отдельный `cli-workspace.mdc` не заводим; запреты в `pluggable-core.mdc` + секция DESIGN «Контракт game/mission». Пересмотреть, если alwaysApply станет шумным после кода резолва.
- [x] `config/workspace.yaml` + хелпер резолва; убрать pilot defaults из `src/**` и выровнять scripts (G1–G2, G9)
  - Хелпер: `resolve_game_mission` / `add_game_mission_arguments` / `apply_resolved_game_mission` в `src/project_paths.py`.
  - G1: нет `default="rushn_attack"|"m1"` в `src/`. G2: `tests/test_workspace_resolve.py`. G9: ручная приёмка (workspace есть → дефолт миссии; без файла/полей → отказ).
- [x] Scout и прочие entry на тот же резолв; отказ от cwd-как-контекста в доках
  - `resolve_cli_reference_fm2` / `resolve_cli_mission_fm2`; `ram_scout`, `build_playthrough`, `record_demos`, `segment_playthrough`.
  - Docs: SCRIPTS / GLOSSARY / DESIGN — без cwd-гибрида; FCEUX `cwd=` = staging.
- [x] CLI-ловушки: wipe states/demos, inference_local wipe, task↔CLI, timesteps, model stem (G3–G5)
  - States: только слоты плана / `--replace-states`. Demos: non-stub без `--force`. Wipe+skip-preflight → error.
  - Task: CLI > task. Continue: явный `--timesteps` < sidecar → exit без `--allow-reduce-target`.
  - Model stem conflict; ram_scout resolve только с `--write-ram-map`.
- [x] Phase isolation / vocabulary из YAML плагина (G6)
  - `policy_heads.isolation.forbid` / `required_phases`; `PhaseAwarePPO` + gate читают spec; RnA env_config обновлён.
- [x] Achievements конфиг под плагин (G7)
  - `games/rushn_attack/achievements.yaml` + `game.yaml` → `achievements`; корневой `config/achievements.yaml` удалён.
  - `load_achievements_config(game_id=…)` / `achievements_config_path`; sort — `playlist_sort` в YAML.
  - Тест: `tests/test_achievements_plugin_path.py`.
- [x] Толстые scripts: план переноса или отсрочка в заметках (G8)
  - План + отсрочка bench/stress → **2026-09-30**; волны **A–C выполнены** в этой сессии (`segment` / `ram_scout` / play FM2).
- [x] SCRIPTS / MEASUREMENTS docs-only cleanup (G10)
  - Gate `force-promote|--no-resume` в SCRIPTS/MEASUREMENTS пуст; workspace в шапке карточек; ops MEASUREMENTS на model-out continue.
- [x] Прогон гейтов G1–G13; не трогать боевой `genN.zip` (G11)
  - См. отметки G1–G13 выше; 64 pytest; genN.zip не трогали.

### Критерий готовности (DoD)

- [x] Пункты A–C закрыты кодом + гейтами или явно отклонены с записью в заметках  
  - Bench/stress/PPU heuristic / `cp_gameplay0` fallback — отсрочка или зафиксированная серая зона (G8/G13).  
- [x] G1–G11 зелёные (G8 допускается «отсрочка» только с явной записью)  
- [x] mdc + DESIGN обновлены; агент не может честно обойти запрет «только if game_id»  
- [x] Проработка в ветке `task/scripts-audit`

### Не делать (антискоуп)

- Гибрид «cwd + workspace + хардкод» как равноправные источники дефолтов  
- Walk-up от cwd для выбора плагина  
- Переписывать архивные TASK ради косметики `--no-resume`  
- Большой рефакторинг BC / multi-head API / bridge IPC «заодно»  
- Удалять пользовательские `models/genN.zip` / эталонные demos  
- Плодить фасады без удаления dual paths  
- Дублировать весь DESIGN в трёх mdc без нужды

### Заметки / гипотезы

**Аудит CLI (2026-07-27):** high/medium/low — см. историю чата; train model-io done.

**Контекст game/mission (решение оператора):** один источник — workspace; без хардкода в ядре; без cwd-гибрида; scout выровнять.

**Аудит Pluggable Core (2026-07-27):** нет `if game_id` в src; серые зоны закрыты или отсрочены: phase isolation из YAML (G6), achievements в плагине (G7), pilot defaults → workspace (G1–G2), толстые scripts A–C + отсрочка bench (G8). Остаток: PPU heuristic / fallback `cp_gameplay0` (таблица C) — не раздувать в этом audit.

**Приёмка гейтов (2026-07-27):** G1–G13 зелёные; pytest audit-сюит **64 passed**; `models/genN.zip` не изменялся.
---

### G8 — план переноса толстых scripts (2026-07-27)

**Критерий «толстый»:** в `scripts/` есть бизнес-логика (доменные функции/классы, не только argv→`src`), обычно ≥~120 строк **или** импорт *из* `scripts/` другими модулями.

**Цель:** `scripts/` = Facade (DESIGN §5); публичный CLI не менять без [регистрации в SCRIPTS](../../DESIGN.md#регистрация-скриптов-в-scriptsmd).

#### Инвентарь

| Скрипт | ~LOC | Запах | Цель в `src/` | Решение |
| --- | ---: | --- | --- | --- |
| `segment_playthrough.py` | ~45 | facade | `playthrough_build.build_demos` | **A done** |
| `ram_scout.py` | ~80 | facade | `src/ram_scout.py` | **B done** |
| `play_inference_fm2.py` | ~55 | facade | `stream.play_fm2` + `fm2_playback` helpers | **C done** |
| `play_fm2_gui.py` | ~55 | facade | `stream.play_fm2.play_gui_fm2` | **C done** |
| `benchmark_bridge.py` | 456 | полный bench IPC | `bench/bridge_metrics.py` (или `train/bench_bridge.py`) | **Отсрочка → 2026-09-30** |
| `benchmark_train.py` | 386 | e2e PPO bench | `bench/train_metrics.py` | **Отсрочка → 2026-09-30** |
| `stress_e2e_gate.py` | 569 | фазы gate / spike | `bench/stress_e2e.py` | **Отсрочка → 2026-09-30** |
| `train_fps_round_prep.py` | 156 | runbook + sha архива gen0 | опц. `train/fps_round_prep.py`; можно оставить CLI | **Отсрочка → 2026-09-30** (низкий приоритет) |
| `build_playthrough.py` | 167 | в основном facade; тянет `segment_playthrough` | после волны A — только argv | OK после A |
| `hybrid_episode_prep.py` | 128 | оркестрация playlist+board | оставить facade | OK (тонкий) |
| `run_smoke.py` + smoke_* / parallel | ≤124 | quarantine / suite | оставить в scripts (гигиена) | OK |
| Остальные ≤110 (`record_demos`, `export_fm2`, `*_preflight`, playlist, board, eval, …) | — | argv→src | — | OK |

`stress_parallel_reset` / `bench_parallel_step` (~50 LOC) — тонкие; не G8-перенос. Workspace/CLI для них — пункт A задачи (уже частично закрыт резолвом там, где есть argparse).

#### Волны (follow-up, не блокируют DoD audit при отсрочке bench)

**A — segment → `src/` — done (2026-07-27)**  
- `npz_is_non_stub` / `build_demos` / `_load_human_jsonl` → `src/playthrough_build.py`.  
- `scripts/segment_playthrough.py` — тонкий facade; `build_playthrough` импортирует из `src/`.  
- Тест: `tests/test_cli_traps.py` → `playthrough_build`.

**B — ram_scout launch — done (2026-07-27)**  
- `stage_fm2` / `run_fceux_scout` / `write_candidates_only` / `run_ram_scout` → `src/ram_scout.py`.  
- `scripts/ram_scout.py` — тонкий facade (resolve CLI + print).  
- Тест: `tests/test_ram_scout_module.py` (без FCEUX).

**C — FM2 play (inference + GUI) — done (2026-07-27)**  
- Общие: `stage_rom` / `prepare_playback_fm2` / `wait_fceux_process` / `reset_staging_dir` → `src/fm2_playback.py`.  
- Оркестрация: `src/stream/play_fm2.py` (`play_single_fm2`, `play_playlist`, `play_gui_fm2`, `play_input`).  
- CLI `play_inference_fm2` / `play_fm2_gui` — тонкие facades.  
- Тест: `tests/test_fm2_playback_helpers.py`.

**Отсрочка (антискоуп до даты):** `benchmark_*`, `stress_e2e_gate`, `train_fps_round_prep` — **не переносить в рамках `task/scripts-audit`**. Пересмотр не позже **2026-09-30** (отдельная задача / BACKLOG bench hygiene). Причина: diagnostics/IPC-heavy; антискоуп audit запрещает большой рефакторинг bridge IPC «заодно».

#### Порядок и DoD волны A

- **Done (2026-07-27):** нет `from segment_playthrough import` вне docs; `test_cli_traps` green; SCRIPTS/GLOSSARY обновлены.

#### DoD волны B

- **Done (2026-07-27):** логика в `src/ram_scout.py`; CLI тонкий; unit без FCEUX green.

#### DoD волны C

- **Done (2026-07-27):** helpers в `fm2_playback`; play API в `stream/play_fm2`; CLI facades; unit green.