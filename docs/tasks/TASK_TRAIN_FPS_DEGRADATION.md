# TASK_TRAIN_FPS_DEGRADATION — деградация fps при длительном train

**Статус:** open  
**Ветка:** `task/train-fps-degradation` — проработку этой задачи выполнять **только в этой ветке** (не в `main` и не в чужих task-ветках).  
**Было:** `ISSUE_TRAIN_FPS_DEGRADATION` (вернуто из archive)  
Каркас: [TASK_BLANK.md](TASK_BLANK.md)

**Контекст:** длительный `train_ppo` (8 `SubprocVecEnv`) показывает падение SB3 `fps` с **~6** до **~1** при неизменном `ep_len_mean≈2`. Bridge STEP-only при этом остаётся **~22–23 env-steps/s** ([MEASUREMENTS.md](../MEASUREMENTS.md) §5.0).

**Базовая линия (до проработки):** [MEASUREMENTS.md](../MEASUREMENTS.md) § «Деградация fps — базовая линия».

**Текущий раунд:** [§ Раунд R6 — dual train+measure](#раунд-r6--dual-trainmeasure-2026-07-17) (T0–T5 закрыты; следующий шаг — A/B + продолжение `m1_v0_n6`).

**Связанные отчёты:** [ISSUE_FALL.md](archive/ISSUE_FALL.md) §D (накопительный эффект), [§ Стрессовый smoke](archive/ISSUE_FALL.md#стрессовый-smoke--диагностика) (короткий gate-shaped stress).

---

## Гипотезы (что ищем)

| ID | Гипотеза | Симптом | Приоритет |
| -- | -------- | ------- | --------- |
| **H1** | Накопительная нагрузка сессии (orphan FCEUX / python, фрагментация RAM) | gate 2-й подряд: fps **~6 → ~2** без смены кода | высокий |
| **H2** | Исчерпание RAM → swap при 8 FCEUX + PPO update | рост wall/rollout, OpenBLAS OOM, fps **~1** на длинном train | высокий |
| **H3** | Reset storm + `bridge_load_lock` при `ep_len≈2` | низкий **steady** fps (~5), не объясняет деградацию со временем сам по себе | средний (базовый потолок) |
| **H4** | Деградация FCEUX / IPC latency за часы turbo | рост `ms/step` без timeout; рост файлов в `tmp/bridge/train_*` | средний |
| **H5** | I/O checkpoint (`latest.zip` каждый rollout) | просадка fps на `on_rollout_end`; сравнение с `--no-latest-checkpoint` | низкий |
| **H6** | Термальное trottling CPU | плавное падение после 1+ ч на i7-3770 | низкий |

---

## План нагрузочного тестирования

Цель: **локализовать** вклад H1–H6 и зафиксировать метрики в [MEASUREMENTS.md](../MEASUREMENTS.md) (колонка «после проработки»).

### Предусловия (все прогоны)

1. Перезагрузка ОС или ручная очистка: `taskkill /F /IM fceux64.exe`, нет orphan `python` train/benchmark (см. [train_preflight.py](../SCRIPTS.md#train_preflightpy)).
2. Закрыть лишние приложения; **16 GB RAM** — эталонная среда.
3. Фиксировать в заметках: дата, свободная RAM до/после, JSON-отчёты в `tmp/bench/` / `tmp/smoke/`.
4. Между **сериями** прогонов — полный cleanup (`cleanup_bridge_sessions('train_')` + `bench_`).

---

### Фаза T0 — контроль bridge (регрессия IPC)

**Вопрос:** деградирует ли bridge без PPO?

| Шаг | Команда | Метрики | Критерий «зелёный» |
| --- | ------- | ------- | ------------------ |
| T0.1 | `benchmark_bridge.py --n-envs 8` | `env-steps/s (parallel)`, `ms/step` | ≈ **22–23** env-steps/s (как 5.0) |
| T0.2 | `benchmark_bridge.py --n-envs 8 --ep-len2-cycles 128` | `ep_len2` breakdown, `gate_rollout_projection` | без IPC timeout; reset/step ≈ **1.1** |

```bash
./.venv/Scripts/python.exe scripts/benchmark_bridge.py --n-envs 8
./.venv/Scripts/python.exe scripts/benchmark_bridge.py --n-envs 8 --ep-len2-cycles 128
```

---

### Фаза T1 — накопительный эффект (H1)

**Вопрос:** воспроизводится ли падение fps при повторных e2e без перезагрузки?

| Шаг | Команда | Метрики | Ожидание (базовая линия) |
| --- | ------- | ------- | ------------------------ |
| T1.1 | `benchmark_train.py --mode gate` (чистая машина) | `env_steps_per_s_wall`, `steady`, SB3 `fps` | wall **~5–6**, steady **~6–7** |
| T1.2 | **Сразу** T1.1 повторить без reboot | те же | wall **~2**, steady **~2** (5.0: 5.78 → 1.95) |
| T1.3 | После T1.2: `stress_e2e_gate.py --full` | `report.json` phases | зелёный / красный по фазе |
| T1.4 | После T1.3: снова `benchmark_train.py --mode gate` | wall/steady | зафиксировать ухудшение vs T1.1 |

```bash
./.venv/Scripts/python.exe scripts/benchmark_train.py --mode gate
./.venv/Scripts/python.exe scripts/benchmark_train.py --mode gate
./.venv/Scripts/python.exe scripts/stress_e2e_gate.py --full
./.venv/Scripts/python.exe scripts/benchmark_train.py --mode gate
```

**Вывод по фазе:** если T1.2 ≪ T1.1 — H1 подтверждена; remediation: R0.2 preflight, обязательный cleanup между прогонами.

---

### Фаза T2 — compound RAM / PPO + vec (H2)

**Вопрос:** падает ли fps при одновременно живых 8 FCEUX и PPO update?

| Шаг | Команда | Метрики | Связь |
| --- | ------- | ------- | ----- |
| T2.1 | `stress_e2e_gate.py --phase ppo_spike` | wall, OOM в stderr | изолированный spike |
| T2.2 | `stress_e2e_gate.py --phase ppo_spike_with_vec` | wall, ошибка | compound B4 ([ISSUE_FALL](archive/ISSUE_FALL.md)) |
| T2.3 | `benchmark_train.py --mode fps` | steady env-steps/s | эталон steady **~7** (1-й прогон) |
| T2.4 | `train_ppo.py --n-envs 4 --timesteps 4096` | SB3 fps, RAM | сравнение с `n_envs=8` |

Мониторинг RAM (Диспетчер задач / Performance Monitor): пик на 2-м rollout и при `ppo_spike_with_vec`.

---

### Фаза T3 — длительный train, drift по rollout (H2, H4, H6)

**Вопрос:** растёт ли wall-time одного rollout со временем?

| Шаг | Команда | Длительность | Метрики |
| --- | ------- | ------------ | ------- |
| T3.1 | `train_local.sh --timesteps 50000 --save-every 10000 --checkpoint-out checkpoints/m1_v0_fps_bench.zip` | ~7–14 ч при fps 1–2; **цель ≥10 rollout** | SB3 `fps` по итерациям; **Δ time_elapsed** между rollout 1, 10, 20 |
| T3.2 | То же, но после `test_parallel_env --n-envs 12` без cleanup (негативный контроль) | — | ускоренная деградация? |

**Парсинг лога:** для каждой строки `iterations | N` и `time_elapsed` вычислить `wall_rollout[N] = elapsed[N] - elapsed[N-1]`.

**Критерии:**

| Паттерн | Интерпретация |
| ------- | ------------- |
| `wall_rollout` стабилен (±15%) | деградация артефакт кумулятивного SB3 fps |
| рост `wall_rollout` в 2–4× к rollout 10+ | H2/H4/H6 |
| скачок на rollout 10–12 (~30 мин) как в базовой линии | порог RAM/swap |

```bash
./scripts/train_local.sh --timesteps 50000 --save-every 10000 --checkpoint-out checkpoints/m1_v0_fps_bench.zip
```

Запуск **в отдельном терминале** (не фон агента). Остановка — Ctrl+C; прогресс в `checkpoints/latest.zip`.

---

### Фаза T4 — I/O checkpoint (H5)

| Шаг | Команда | Сравнение |
| --- | ------- | --------- |
| T4.1 | `benchmark_train.py --mode gate` (default: `--latest-checkpoint` on) | wall/steady |
| T4.2 | обёртка: `train_ppo.py ... --no-latest-checkpoint --timesteps 2048` | SB3 fps |

Ожидание: вклад H5 **небольшой** (<10% wall); если больше — throttling save (реже `latest`).

---

### Фаза T5 — приёмка после фиксов

Повторить **минимальный набор**:

1. T0.1 (bridge)
2. T1.1 + T1.2 (накопление)
3. T3.1 (длительный train, ≥10 rollout)

Заполнить колонку **«после проработки»** в [MEASUREMENTS.md](../MEASUREMENTS.md).

---

## Матрица: тест → гипотеза → артефакт

| Фаза | H1 | H2 | H3 | H4 | H5 | H6 | JSON / лог |
| ---- | -- | -- | -- | -- | -- | -- | ---------- |
| T0 bridge | | | ✓ базовый потолок | ✓ | | | `tmp/bench/bridge_baseline/` |
| T1 gate ×2 | ✓ | частично | | | | | `tmp/bench/train_e2e_*/train_report.json` |
| T2 stress spike | | ✓ | | | | | `tmp/smoke/stress_e2e/report.json` |
| T3 long train | ✓ | ✓ | | ✓ | ✓ | ✓ | stdout train, `latest.zip` |
| T4 no-latest | | | | | ✓ | | stdout |

---

## Ожидаемые remediation (после подтверждения гипотез)

| Гипотеза | Направление работ | Ссылка BACKLOG / FAIL |
| -------- | ----------------- | --------------------- |
| H1 | жёсткий preflight, kill orphan python+FCEUX | R0.1, R0.2 |
| H2 | `n_envs` 4–6 на 16 GB; gc между rollout; restart из `latest.zip` | R3.2, R3.3 |
| H3 | reward/curriculum → длиннее эпизоды | ML_CONCEPT |
| H4 | периодический restart FCEUX; очистка `tmp/bridge/train_*` | follow-up |
| H5 | реже `latest` или async save | follow-up |
| H6 | документировать лимит сессии; паузы | ops |

---

## Статус плана

| Фаза | Статус | Дата | Заметки |
| ---- | ------ | ---- | ------- |
| T0 | **выполнено** | 2026-07-14 | parallel **25.34** (128 steps); ep_len2 reset/step **1.03** |
| T1 | **выполнено** | 2026-07-14 | H1 подтверждена (5.0); T1.4 после stress: wall **6.26** (не ухудшился) |
| T2 | **выполнено** | 2026-07-14 | ppo_spike OK; n_envs=4 fps **6–9** vs n_envs=8 steady **5.62** |
| T3 | **частично** | 2026-07-14 | T3.1 базовая линия; T3.✓ вывод по `wall_rollout`; T3.2 отложен |
| T4 | **выполнено** | 2026-07-14 | H5: latest **~18%** wall (405 vs 333 s) |
| T5 | **выполнено** | 2026-07-14 | T5.3 train `n_envs=6` 27 rollout, **6658 s** |
| **R6** | **R6.0 done** | 2026-07-17 | archive + `m1_v0_n6`; A/B + long — чеклист § R6 |

---

## Связанные документы

| Документ | Содержание |
| -------- | ---------- |
| [MEASUREMENTS.md](../MEASUREMENTS.md) | Сводные метрики; § деградация fps |
| [SCRIPTS.md](../SCRIPTS.md) | Команды benchmark / train / stress |
| [GLOSSARY.md](../GLOSSARY.md) § [Train log](../GLOSSARY.md#train-log-rollout-table) | Разбор вывода train в консоль — **устарел**, см. [§ Docs](#docs--glossary-train-log) |
| [ISSUE_FALL.md](archive/ISSUE_FALL.md) | Инцидент gate, stress-диагностика, план R0–R5 |

---

## Чеклист выполнения (T0–T5)

Отмечать по мере выполнения. Критерий фазы — все шаги фазы `[x]`.

**Критерий закрытия плана:** T5 пройден; колонка **«после проработки»** в [MEASUREMENTS.md](../MEASUREMENTS.md) заполнена; gate 2/2 wall ≥80% от gate 1/2; SB3 fps (rollout 20+) ≥4.

### T0 — контроль bridge (регрессия IPC)

- [x] **T0.1** `benchmark_bridge.py --n-envs 8` — **25.34** env-steps/s (2026-07-14, `--parallel-steps 128`)
- [x] **T0.2** `benchmark_bridge.py --n-envs 8 --ep-len2-cycles 128` — без IPC timeout; reset/step **1.03**

### T1 — накопительный эффект (H1)

- [x] **T1.1** `benchmark_train.py --mode gate` (чистая машина) — wall **5.78**, steady **7.1** (5.0, 2026-07-13)
- [x] **T1.2** gate **сразу повторить** без reboot — wall **1.95**, steady **2.2** (H1 подтверждена)
- [x] **T1.3** после T1.2: `stress_e2e_gate.py --full` — зелёный, **509 s**, bridge **21.72** env-steps/s (2026-07-14)
- [x] **T1.4** после T1.3: `benchmark_train.py --mode gate` — wall **6.26**, steady **7.77** (vs T1.1 **5.78** — без ухудшения)

### T2 — compound RAM / PPO + vec (H2)

- [x] **T2.1** `stress_e2e_gate.py --phase ppo_spike` — OK **3.8 s**, без OOM (в составе T1.3)
- [x] **T2.2** `stress_e2e_gate.py --phase ppo_spike_with_vec` — OK **6.6 s**, FCEUX alive (T1.3)
- [x] **T2.3** `benchmark_train.py --mode fps` — steady **5.62** env-steps/s (8192 steps, 2026-07-14)
- [x] **T2.4** `train_ppo.py --n-envs 4 --timesteps 4096` — SB3 fps **6–9** (final **8**), wall **457 s**

### T3 — длительный train, drift по rollout (H2, H4, H6)

- [x] **T3.1** `train_local.sh --timesteps 50000 ...` — базовая линия зафиксирована (2026-07-13/14, ~10.5 ч); `wall_rollout` в [MEASUREMENTS.md](../MEASUREMENTS.md)
- [ ] **T3.2** (негативный контроль) `test_parallel_env --n-envs 12` без cleanup → длинный train — *отложено: требует 7–14 ч train*
- [x] **T3.✓** Вывод: рост `wall_rollout` **~150 → ~650 с** (rollout 10+, **4×**); скачок rollout 11–12 (~30 мин) → **H2** (RAM/swap); bridge стабилен

### T4 — I/O checkpoint (H5)

- [x] **T4.1** `benchmark_train.py --mode gate` (default `--latest-checkpoint` on) — wall **5.05**, steady **6.92** (2026-07-14)
- [x] **T4.2** `train_ppo.py ... --no-latest-checkpoint --timesteps 2048` — wall **333 s**, SB3 fps **5–6**
- [x] **T4.✓** Вывод: H5 **~18%** wall (405 vs 333 s); не главный bottleneck vs H1/H2

### T5 — приёмка после фиксов

- [x] **T5.1** повтор T0.1 (bridge) — **26.00** env-steps/s (2026-07-14)
- [x] **T5.2** повтор T1.1 + T1.2 (накопление, `n_envs=8` gate): **3.81** → **1.52** wall (**40%**); H1 на gate **не закрыта**
- [x] **T5.3** `train_local.sh --timesteps 20000 --n-envs 6` — **27 rollout**, wall **6658 s**, fps **2→3**; rollout 10 wall **273 s**, rollout 20 **99 s** (vs базовая **~650 s**)
- [x] **T5.4** колонка **«после проработки»** в [MEASUREMENTS.md](../MEASUREMENTS.md) заполнена (T5.3)
- [x] **T5.✓** План T5 закрыт (H1 на gate 8×2 — открытый follow-up; длинный train H2 — улучшение)

### Remediation (после подтверждения гипотез)

Связь с [ISSUE_FALL.md](archive/ISSUE_FALL.md) § R0–R3.

- [x] **H1** preflight + kill orphan (`R0.1`, `R0.2`) — закрыто в [5.0]
- [x] **H2** (частично) `OPENBLAS`/`torch` thread limits (`R3.1`); фаза `ppo_spike_with_vec` (`R3.2`)
- [x] **H2** (при необходимости) `gc.collect()` между rollout (`R3.3`); `n_envs` 4–6 на 16 GB — `RolloutGcCallback`, `train_local.sh --n-envs 6`, warn при `n_envs>6`
- [ ] **H3** reward/curriculum → длиннее эпизоды (ML_CONCEPT)
- [ ] **H4** периодический restart FCEUX; очистка `tmp/bridge/train_*`
- [ ] **H5** throttling `latest.zip` или async save
- [ ] **H6** документировать лимит сессии; паузы (ops)

---

## Раунд R6 — dual train+measure (2026-07-17)

**Статус:** запланирован; среда подготовлена (код + prep-скрипт).

**Цель раунда:** закрыть пробелы T0–T5 (оптимальность `n_envs`, телеметрия H2) **без порчи** накопленных весов, и по возможности **дополнить обучение** на длинном прогоне.

**Модерация T0–T5 (кратко):** `n_envs=6` — pragmatic mitigation, не доказанный оптимум; bridge не деградирует; H2 принята по wall-cliff без RAM-логов; цель fps≥4 не достигнута; рычаги H3–H5 открыты.

### Инвентарь чекпоинтов (не трогать / как продолжать)

| Файл | n_envs | steps | Роль в R6 |
| ---- | ------ | ----- | --------- |
| `checkpoints/m1_v0.zip` | 4 | 4096 | **FROZEN** — короткий smoke-наследник имени; не resume, не overwrite |
| `checkpoints/m1_v0_fps_t5.zip` | 6 | 20736 | **FROZEN** артефакт T5.3; источник promote |
| `checkpoints/m1_v0_n6.zip` | 6 | ← копия t5 | **PRIMARY** боевая линия: resume + raise target |
| `checkpoints/archive/YYYYMMDD_*.zip` | — | — | страховочная копия frozen до старта |

Prep (один раз перед раундом):

```bash
./.venv/Scripts/python.exe scripts/train_fps_round_prep.py
# при необходимости: --target-timesteps 100000 --force-promote
```

### Правила безопасности

1. Короткие A/B — **только** `--smoke` → `tmp/smoke/` (не `games/.../checkpoints/`).
2. Длинный dual — **только** `--checkpoint-out checkpoints/m1_v0_n6.zip` + `--n-envs 6` (sidecar mismatch иначе abort).
3. Не запускать long с `--checkpoint-out checkpoints/m1_v0.zip` / `m1_v0_fps_t5.zip`.
4. Resume: `--timesteps N` при `N > sidecar.target` **поднимает** цель (см. `resolve_target_timesteps`); иначе «target already reached».
5. Между сериями — `train_preflight.py`; перед long предпочтителен reboot (H1).
6. Метрики — `tmp/bench/<session>/rollouts.jsonl` (`--rollout-metrics`); не смешивать с mission logs inference.

### План прогонов (~7–10 ч wall)

| ID | Тип | Команда / суть | Wall | Учит модель? |
| -- | --- | -------------- | ---- | ------------ |
| **R6.0** | prep | `train_fps_round_prep.py` | <1 мин | нет |
| **R6.1** | short A/B | smoke `n_envs∈{4,6,8}` × 4096; preflight между | ~1–1.5 ч | нет (tmp) |
| **R6.2** | long dual | resume `m1_v0_n6` → target **100k**, metrics on | ~2–4 ч | **да** |
| **R6.3** | optional | smoke `n=8`+gc ≥20 rollout **или** long `n=8` в **отдельный** `m1_v0_n8_exp.zip` | ~2–3.5 ч | только если отдельная линия |
| **R6.4** | parse | `parse_train_rollouts.py --jsonl …/rollouts.jsonl` | <1 мин | нет |

Рекомендуемый боевой long (после prep):

```bash
./.venv/Scripts/python.exe scripts/train_preflight.py
./scripts/train_local.sh --n-envs 6 --timesteps 100000 --save-every 10000 \
  --checkpoint-out checkpoints/m1_v0_n6.zip \
  --rollout-metrics --rollout-metrics-session fps_r6_YYYYMMDD
```

Короткий A/B (пример `n=6`; повторить для 4 и 8):

```bash
./.venv/Scripts/python.exe scripts/train_preflight.py
./.venv/Scripts/python.exe src/train/train_ppo.py --smoke \
  --smoke-session fps_r6_ab_n6 --n-envs 6 --timesteps 4096 --no-bc \
  --rollout-metrics --rollout-metrics-session fps_r6_ab_n6
```

Сводка:

```bash
./.venv/Scripts/python.exe scripts/parse_train_rollouts.py \
  --jsonl tmp/bench/fps_r6_YYYYMMDD/rollouts.jsonl
```

### Критерии выводов R6

| Вопрос | Метрика | Вердикт |
| ------ | ------- | ------- |
| `n=6` всё ещё стабилен на long? | `wall_late/early < 2`, нет crash | держим primary |
| `n=8`+gc лучше/хуже на short? | steady env-steps/s, avail_phys_mb | решать про R6.3 |
| H2 = RAM? | падение `avail_phys_mb` коррелирует с ростом wall | да / нет / смешанно |
| Цель fps≥4? | rate last5 / SB3 fps rollout 20+ | достигнута / нет |

Заполнить в [MEASUREMENTS.md](../MEASUREMENTS.md) секцию **«R6 dual train+measure»**.

### Пути роста производительности (после R6, железо i7-3770 / 16 GB)

Порядок — по ожидаемому ROI при текущем hardware; **не** начинать с нового IPC-транспорта (bridge уже ~25 env-steps/s и не деградирует).

| Приоритет | Путь | Условие / триггер | Ожидаемый эффект |
| --------- | ---- | ----------------- | ---------------- |
| **P0** | Зафиксировать default `n_envs` по данным R6 (6 / 7 / 8+gc) | R6.1–R6.3 | стабильный long без ×4 wall |
| **P1** | **H3** — длиннее эпизоды (reward / curriculum, ML_CONCEPT) | всегда полезно для ML | рост steady fps + качество данных |
| **P2** | **H5** — реже / async `latest.zip` | вклад ≥10% на long | −10–20% wall |
| **P3** | **H4** — periodic FCEUX recycle / mid-session restart из `latest` | wall растёт при стабильной RAM | снять накопление без снижения env |
| **P4** | **H1** ops — reboot/preflight между сериями gate | gate 2/2 <80% | воспроизводимость бенчей |
| **P5** | IPC v2 / shared mem | только если после P0–P3 e2e/bridge всё ещё ≪0.3 **и** ms/step доминирует | низкий ROI (1.8 уже FAIL) |
| **P6** | Больше RAM / другое железо | Commit≈16 GB + page faults на `n≥8` | поднять parallel env |

**Не делать в R6:** менять `bridge.lua` ради throughput; `--force-promote` после того, как `m1_v0_n6` уже ушёл дальше t5; смешивать A/B `n_envs` в одном resume.

### Чеклист R6

- [x] **R6.0** `train_fps_round_prep.py` — archive + `m1_v0_n6` + manifest (2026-07-17)
- [ ] **R6.1a** smoke n=4 × 4096 + metrics
- [ ] **R6.1b** smoke n=6 × 4096 + metrics (preflight перед)
- [ ] **R6.1c** smoke n=8 × 4096 + metrics (preflight перед)
- [ ] **R6.2** long resume `m1_v0_n6` → ≥100k, ≥20 rollout после start, metrics on
- [ ] **R6.3** (опц.) отдельная линия n=8 **или** отложить
- [ ] **R6.4** `parse_train_rollouts` + запись в MEASUREMENTS
- [ ] **R6.docs** актуализировать [GLOSSARY § Train log](../GLOSSARY.md#train-log-rollout-table) — см. [§ Docs](#docs--glossary-train-log)
- [ ] **R6.✓** выбрать default `n_envs` + приоритет P0–P3 на следующий код-цикл

### Docs — GLOSSARY Train log

**Статус:** open (блокер закрытия R6 по документации, не по прогонам).

[GLOSSARY.md](../GLOSSARY.md) § **Train log (rollout table)** (якорь `#train-log-rollout-table`, ~стр. 143–176) описывает только устаревший «Периодический вывод» SB3 (`verbose=1` + `progress_pct` / `target_timesteps`). После R6 в консоли при `--rollout-metrics` есть **два** потока; глоссарий должен разбирать оба.

| Поток | Откуда | Когда | Что документировать |
| ----- | ------ | ----- | ------------------- |
| Таблица SB3 | `model.learn(verbose=1)` + `TrainProgressPctCallback` | каждый rollout (как раньше) | `ep_len_mean`, `ep_rew_mean`, кумулятивный `fps`, `iterations`, `time_elapsed`, `total_timesteps`, `progress_pct`, `target_timesteps`; явно: SB3 `fps` ≠ per-rollout rate |
| Строка `rollout_metrics:` | `RolloutMetricsCallback` (`src/train/rollout_metrics.py`) | каждый rollout при `--rollout-metrics` | пример: `rollout_metrics: #N wall=…s steps=… rate=… avail_ram_mb=…`; поля = `wall_rollout_s`, `delta_timesteps`, `env_steps_per_s`, `avail_phys_mb` |
| JSONL | `tmp/bench/<session>/rollouts.jsonl` | тот же callback | схема строки + сводка `parse_train_rollouts.py` (`wall_late/early`, `degraded`) |

**DoD R6.docs:**

- [ ] Пример консоли обновлён (SB3-таблица **и** строка `rollout_metrics:`)
- [ ] Таблица полей: старые SB3 + новые (`wall`, `rate` / `env_steps_per_s`, `avail_ram_mb` / `avail_phys_mb`)
- [ ] Явно: кумулятивный SB3 `fps` vs per-rollout `rate` (для H2/деградации смотреть `rate` / `wall_rollout`, не только `fps`)
- [ ] Ссылка на `--rollout-metrics` / `--no-progress-pct` и на [MEASUREMENTS.md](../MEASUREMENTS.md) § R6
- [ ] Якорь `#train-log-rollout-table` и ссылки на `time_elapsed` / wall-clock в глоссарии не сломаны

### Код среды (готово к запуску)

| Компонент | Назначение |
| --------- | ---------- |
| `src/train/rollout_metrics.py` | `RolloutMetricsCallback` + RAM snapshot (Windows) |
| `train_ppo --rollout-metrics` | JSONL в `tmp/bench/<session>/rollouts.jsonl` |
| `resolve_target_timesteps` | resume может поднять `target` через CLI |
| `scripts/train_fps_round_prep.py` | archive frozen, promote `m1_v0_n6`, печать команд |
| `scripts/parse_train_rollouts.py` | сводка wall / degradation flag |
