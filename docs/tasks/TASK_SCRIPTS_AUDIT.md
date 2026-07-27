# TASK_SCRIPTS_AUDIT — аудит публичного CLI (ловушки артефактов)

**Статус:** open  
**Приоритет:** high  
**Ветка:** `task/scripts-audit` — проработку этой задачи выполнять только в этой ветке.  
**Зависит от:** безопасный контракт train `model-in`/`model-out` (done на `main`: continue / from_ancestor / scratch)  
**Файлы:** `docs/SCRIPTS.md`, `scripts/*`, `src/train/train_ppo.py`, `src/stream/run_inference.py`, `src/playthrough_build.py`, `scripts/build_playthrough.py`, `scripts/inference_local.sh`, `scripts/train_local.sh`  
**Контекст в чат:** этот файл + [SCRIPTS.md](../SCRIPTS.md) + [DESIGN.md § регистрация скриптов](../DESIGN.md#регистрация-скриптов-в-scriptsmd) + [гигиена артефактов](../DESIGN.md#гигиена-артефактов)

### Цель

Пройти публичный CLI (`scripts/`, `train_ppo`, `run_inference`) и убрать паттерны того же класса, что бывшая ловушка `--resume` / молчаливый wipe: опасные дефолты, silent override флагов, dual paths shell↔Python, docs-only / legacy флаги. Принцип: скрипт либо отказывается, либо делает ожидаемо; не стартует «в любом случае» ценой артефактов.

Ориентир приоритетов (из аудита 2026-07-27):

1. Защита demos / save_states от молчаливого wipe.  
2. Честные конфликты: task JSON↔CLI, `--timesteps`↔sidecar, `--model`↔`--model-version`.  
3. Один канон defaults: shell = preflight + passthrough, логика в Python.  
4. Вычистить docs-only флаги из живых SCRIPTS / MEASUREMENTS.

### Чеклист сессии

- [ ] Зафиксировать матрицу «high / medium / low» в заметках ниже (или сузить до high+medium); сверить с кодом на текущем `main`
- [ ] `build_playthrough`: не удалять все `save_states/*.fc0` без явного replace; не затирать non-stub `demos_for_bc` без force
- [ ] `inference_local.sh`: комбинация `--wipe-gen-logs` + `--skip-preflight` — error или гарантированный wipe; не «съедать» флаг молча
- [ ] `train_ppo` + `--task`: CLI vs JSON — warn/exit при конфликте; deprecate `checkpoint_in`/`checkpoint_out`
- [ ] Continue: понижение `--timesteps` ниже sidecar — не молча; явный флаг или exit
- [ ] Свести defaults `train_local`/`inference_local` к passthrough (канон в Python)
- [ ] `--model` / `--model-version`: exit при расхождении stem
- [ ] Живые доки: убрать `--force-promote`, хвосты `--resume`/`--no-resume` из SCRIPTS/MEASUREMENTS help; archive не переписывать без нужды
- [ ] По [алгоритму регистрации](../DESIGN.md#регистрация-скриптов-в-scriptsmd) обновить `docs/SCRIPTS.md` на каждое изменение публичного CLI
- [ ] Unit/смоук на отказы (tmp_path / quarantine); **не** портить mission `models/genN.zip`

### Критерий готовности (DoD)

- [ ] High-risk пункты закрыты кодом + тестами или явно отклонены с записью в заметках
- [ ] Нет молчаливого wipe demos/save_states/logs без явного флага
- [ ] Конфликты task↔CLI и model↔model-version не silent
- [ ] `docs/SCRIPTS.md` синхронизирован; docs-only несуществующих флагов нет
- [ ] Проработка шла в ветке `task/scripts-audit`

### Не делать (антискоуп)

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
