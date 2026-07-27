# TASK_SCRIPTS_AUDIT — аудит публичного CLI (ловушки артефактов)

**Статус:** open  
**Приоритет:** high  
**Ветка:** `task/scripts-audit` — проработку этой задачи выполнять только в этой ветке.  
**Зависит от:** безопасный контракт train `model-in`/`model-out` (done на `main`: continue / from_ancestor / scratch)  
**Файлы:** `docs/SCRIPTS.md`, `docs/DESIGN.md`, `docs/GLOSSARY.md`, `config/workspace.yaml` (новый), `src/project_paths.py` (или тонкий `cli_defaults`), `scripts/*`, `src/train/train_ppo.py`, `src/stream/run_inference.py`, `src/playthrough_build.py`, `scripts/build_playthrough.py`, `scripts/ram_scout.py`, `scripts/inference_local.sh`, `scripts/train_local.sh`  
**Контекст в чат:** этот файл + [SCRIPTS.md](../SCRIPTS.md) + [DESIGN.md § Pluggable Core / регистрация скриптов](../DESIGN.md) + [гигиена артефактов](../DESIGN.md#гигиена-артефактов)

### Цель

Пройти публичный CLI (`scripts/`, `train_ppo`, `run_inference`) и убрать паттерны того же класса, что бывшая ловушка `--resume` / молчаливый wipe: опасные дефолты, silent override флагов, dual paths shell↔Python, docs-only / legacy флаги. Принцип: скрипт либо отказывается, либо делает ожидаемо; не стартует «в любом случае» ценой артефактов.

Дополнительно — **единый источник контекста игра/миссия** без строк плагина в ядре и без cwd-магии:

1. **Конфиг рабочей области** (`config/workspace.yaml` или согласованное имя): единственный источник дефолтов `game` / `mission` для CLI.  
2. **Без дефолтных id плагина в `src/`** (никакого `default="rushn_attack"` / `"m1"` в argparse ядра) — иначе риск писать артефакты не в ту миссию.  
3. **Один подход для всех скриптов**, включая scout: явные `--game` / `--mission` и/или workspace; **не** определять игру/миссию по текущему каталогу запуска (cwd). Исторический перекос «scout из папки игры/миссии» выровнять под общий канон.

Приоритеты аудита ловушек (2026-07-27):

1. Защита demos / save_states от молчаливого wipe.  
2. Честные конфликты: task JSON↔CLI, `--timesteps`↔sidecar, `--model`↔`--model-version`.  
3. Shell = preflight + passthrough; логика и резолв game/mission — в Python.  
4. Вычистить docs-only флаги из живых SCRIPTS / MEASUREMENTS.

### Контракт резолва game / mission (зафиксировано)

**Один источник дефолтов — workspace-конфиг.** Не гибрид «cwd + yaml + хардкод».

```text
CLI --game / --mission (если заданы) — побеждают
  → иначе поля из config/workspace.yaml
    → иначе SystemExit: укажите флаги или заполните workspace
```

- В `src/**` argparse: `default=None` для game/mission; заполнение только через общий хелпер.  
- Явные флаги — осознанный override оператора, не второй «тихий» дефолт в коде.  
- **Антискоуп этого контракта:** угадывание по `Path.cwd()` / walk-up от cwd к `games/…/missions/…` как способ выбрать плагин.  
- `ram_scout` / shell vs mission: scope по **пути к FM2** и флагам (`--game` / `--mission` / workspace), не по тому, из какой папки вызвали скрипт. (Технический `cwd=` у subprocess FCEUX для staging FM2 — не путать с выбором плагина.)

Статья в [GLOSSARY](../GLOSSARY.md) (добавить при реализации): кратко «конфиг рабочей области» — файл в `config/`, дефолт игры/миссии для CLI; не путать с плагином `games/<id>/` и с `fceux/runtime.yaml`.

### Чеклист сессии

- [ ] Зафиксировать матрицу «high / medium / low» в заметках ниже (или сузить до high+medium); сверить с кодом на текущем `main`
- [ ] Ввести `config/workspace.yaml` + хелпер резолва; убрать `default="rushn_attack"` / `"m1"` из `src/**` (и выровнять scripts)
- [ ] `ram_scout` и родственные entry: тот же резолв game/mission; документировать отказ от cwd-как-контекста; обновить SCRIPTS
- [ ] `build_playthrough`: не удалять все `save_states/*.fc0` без явного replace; не затирать non-stub `demos_for_bc` без force
- [ ] `inference_local.sh`: комбинация `--wipe-gen-logs` + `--skip-preflight` — error или гарантированный wipe; не «съедать» флаг молча
- [ ] `train_ppo` + `--task`: CLI vs JSON — warn/exit при конфликте; deprecate `checkpoint_in`/`checkpoint_out`
- [ ] Continue: понижение `--timesteps` ниже sidecar — не молча; явный флаг или exit
- [ ] Свести `train_local`/`inference_local` к passthrough (без своих хардкод game/mission)
- [ ] `--model` / `--model-version`: exit при расхождении stem
- [ ] Живые доки: убрать `--force-promote`, хвосты `--resume`/`--no-resume` из SCRIPTS/MEASUREMENTS help; archive не переписывать без нужды
- [ ] DESIGN / GLOSSARY: workspace + запрет id плагина в ядре; [алгоритм регистрации](../DESIGN.md#регистрация-скриптов-в-scriptsmd) → SCRIPTS на каждое изменение CLI
- [ ] Unit на резолв (tmp_path, синтетический workspace); **не** портить mission `models/genN.zip`

### Критерий готовности (DoD)

- [ ] High-risk пункты закрыты кодом + тестами или явно отклонены с записью в заметках
- [ ] Нет молчаливого wipe demos/save_states/logs без явного флага
- [ ] В `src/**` нет строковых дефолтов id пилотной игры/миссии; дефолты только из workspace (или обязательные флаги)
- [ ] Публичные скрипты (включая scout) выбирают игру/миссию одним каноном; cwd не является источником `game_id`/`mission_id`
- [ ] Конфликты task↔CLI и model↔model-version не silent
- [ ] `docs/SCRIPTS.md` (+ GLOSSARY/DESIGN по необходимости) синхронизированы; docs-only несуществующих флагов нет
- [ ] Проработка шла в ветке `task/scripts-audit`

### Не делать (антискоуп)

- Гибрид «cwd + workspace + хардкод» как равноправные источники дефолтов
- Walk-up от cwd для выбора плагина «для удобства»
- Переписывать архивные TASK ради косметики `--no-resume` в copy-paste
- Большой рефакторинг BC / multi-head / bridge IPC
- Удалять пользовательские `models/genN.zip` / эталонные demos «для чистоты»
- Плодить новые CLI-фасады без удаления старых dual paths

### Заметки / гипотезы

**Аудит (черновик, 2026-07-27):**

High: wipe всех `*.fc0` в `build_playthrough`; stub demos поверх `record_demos`; `inference_local` wipe+skip-preflight; `apply_task_defaults` перебивает CLI; `ram_scout` mission переписывает resolve.

Medium: timesteps не понижается на continue; n_envs 6 vs 8 shell/python; model vs model-version; latest.zip default on; `--live` подмена fceux.cfg; eval_achievements in-place; smoke_env `--log` в mission logs; boolean-стиль / fail-fast no-op; dual demos/stress/task entry.

Low: SCRIPTS `--force-promote` без кода; MEASUREMENTS/`train_fps_round_prep` help «resume»; `stress_parallel_reset` устарел vs gate; `checkpoint_*` aliases.

Train model-io уже: continue / from_ancestor / scratch + `--overwrite-model-out` (не повторять в этой задаче).

**Контекст game/mission (2026-07-27, решение оператора):**

- Не оставлять хардкод плагина в ядре (даже «опциональный» argparse default).  
- Не строить гибрид cwd+yaml: один источник дефолтов — workspace-конфиг; CLI — явный override.  
- Исторический cwd-подход у scout выбивается из остальных скриптов — выровнять под общий канон (удобство cd в миссию не ценим выше единого контракта).  
- Боль «обязательно помнить --game из корня / нестабильный cwd в IDE» признана; снимается workspace-файлом в git, не угадыванием каталога.
