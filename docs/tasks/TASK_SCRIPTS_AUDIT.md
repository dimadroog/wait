# TASK_SCRIPTS_AUDIT — аудит публичного CLI + гигиена Pluggable Core

**Статус:** open  
**Приоритет:** high  
**Ветка:** `task/scripts-audit` — проработку этой задачи выполнять только в этой ветке.  
**Зависит от:** безопасный контракт train `model-in`/`model-out` (done на `main`: continue / from_ancestor / scratch)  
**Файлы:** `docs/SCRIPTS.md`, `docs/DESIGN.md`, `docs/GLOSSARY.md`, `.cursor/rules/pluggable-core.mdc`, `.cursor/rules/` (новые mdc при необходимости), `config/workspace.yaml` (новый), `src/project_paths.py` (или тонкий `cli_defaults`), `scripts/*`, `src/train/*`, `src/stream/*`, `src/achievements/*`, `src/fm2_playback.py`, `src/playthrough_build.py`, `config/achievements.yaml` → перенос под плагин  
**Контекст в чат:** этот файл + [SCRIPTS.md](../SCRIPTS.md) + [DESIGN.md](../DESIGN.md) + [pluggable-core.mdc](../../.cursor/rules/pluggable-core.mdc)

Каркас: [TASK_BLANK.md](TASK_BLANK.md)

### Цель

1. Убрать CLI-ловушки того же класса, что бывший `--resume` / молчаливый wipe: опасные дефолты, silent override, dual paths shell↔Python, docs-only флаги.  
2. Ввести **один** источник дефолтов игра/миссия (`config/workspace.yaml`); убрать id плагина из argparse ядра; выровнять scout и прочие скрипты (без cwd-как-контекста).  
3. Закрыть **серые зоны Pluggable Core**, куда агент пролезает без `if game_id`: словарь фаз пилота в train, PPU-эвристики, achievements вне `games/`, толстые `scripts/`.  
4. Усилить [pluggable-core.mdc](../../.cursor/rules/pluggable-core.mdc) и [DESIGN.md](../DESIGN.md); при необходимости выделить отдельные alwaysApply/globs mdc.

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

Статья в [GLOSSARY](../GLOSSARY.md) (при реализации): «конфиг рабочей области» — `config/workspace.yaml`; не путать с плагином `games/<id>/` и с `fceux/runtime.yaml`.

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

- [ ] **G1 — нет pilot id в argparse src:** `rg 'default=["\']rushn_attack["\']|default=["\']m1["\']' src/` → пусто (после миграции на workspace).  
- [ ] **G2 — резолв:** unit на хелпер: CLI > workspace > SystemExit; cwd не влияет (менять cwd в тесте).  
- [ ] **G3 — model stem conflict:** unit: разные `--model` / `--model-version` → exit.  
- [ ] **G4 — task vs CLI:** unit/хелпер: конфликт timesteps/model_* → exit или CLI wins (зафиксировать одно поведение + тест).  
- [ ] **G5 — wipe demos/states:** unit: non-stub npz и «лишний» `.fc0` не удаляются без явного replace/force.  
- [ ] **G6 — phase vocabulary:** unit: isolation/required phases читаются из синтетического YAML плагина; в `src/train` нет захардкоженных кортежей `("title","intro")` как единственного правила (или они помечены deprecated и покрыты тестом «из YAML»).  
- [ ] **G7 — achievements path:** загрузка конфига номинаций идёт из-под `games/<id>/` (или путь из game.yaml); unit с tmp plugin tree.  
- [ ] **G8 — facade smell (мягкий):** список «толстых» scripts в заметках; для каждого — либо перенос в `src/`, либо явная отсрочка в антискоупе с датой.

Ручные / операторские:

- [ ] **G9:** команда train/inference **без** `--game`/`--mission` при валидном workspace пишет только в указанную миссию; при отсутствии workspace — отказ, не RnA.  
- [ ] **G10:** `docs/SCRIPTS.md` + DESIGN/GLOSSARY синхронизированы; `rg 'force-promote|--no-resume' docs/SCRIPTS.md docs/MEASUREMENTS.md` — нет живых ложных флагов.  
- [ ] **G11:** `pytest` затронутых тестов; mission `models/genN.zip` не меняется.

Регрессия Pluggable Core (документировать в DESIGN, гонять в CI по возможности):

- [ ] **G12:** `rg 'if game_id\s*==' src/` → пусто.  
- [ ] **G13:** нет новых room/pose-литералов RnA в `src/` (выборочный review + запрет в mdc).

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

- [ ] Усилить `pluggable-core.mdc` + DESIGN (+ GLOSSARY workspace); решить: нужен ли отдельный `cli-workspace.mdc`
- [ ] `config/workspace.yaml` + хелпер резолва; убрать pilot defaults из `src/**` и выровнять scripts (G1–G2, G9)
- [ ] Scout и прочие entry на тот же резолв; отказ от cwd-как-контекста в доках
- [ ] CLI-ловушки: wipe states/demos, inference_local wipe, task↔CLI, timesteps, model stem (G3–G5)
- [ ] Phase isolation / vocabulary из YAML плагина (G6)
- [ ] Achievements конфиг под плагин (G7)
- [ ] Толстые scripts: план переноса или отсрочка в заметках (G8)
- [ ] SCRIPTS / MEASUREMENTS docs-only cleanup (G10)
- [ ] Прогон гейтов G1–G13; не трогать боевой `genN.zip` (G11)

### Критерий готовности (DoD)

- [ ] Пункты A–C закрыты кодом + гейтами или явно отклонены с записью в заметках  
- [ ] G1–G11 зелёные (G8 допускается «отсрочка» только с явной записью)  
- [ ] mdc + DESIGN обновлены; агент не может честно обойти запрет «только if game_id»  
- [ ] Проработка в ветке `task/scripts-audit`

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

**Аудит Pluggable Core (2026-07-27):** нет `if game_id` в src; серые зоны — phase literals + isolation gate, PPU heuristic, achievements вне games/, pilot defaults, толстые scripts. Детальный разбор — в чате / agent transcript «Find pluggable-core violations».
