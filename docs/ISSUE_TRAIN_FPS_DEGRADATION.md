# ISSUE_TRAIN_FPS_DEGRADATION — деградация fps при длительном train

**Контекст:** длительный `train_ppo` (8 `SubprocVecEnv`) показывает падение SB3 `fps` с **~6** до **~1** при неизменном `ep_len_mean≈2`. Bridge STEP-only при этом остаётся **~22–23 env-steps/s** ([MEASUREMENTS.md](MEASUREMENTS.md) §5.0).

**Базовая линия (до проработки):** [MEASUREMENTS.md](MEASUREMENTS.md) § «Деградация fps — базовая линия».

**Связанные отчёты:** [ISSUE_FALL.md](ISSUE_FALL.md) §D (накопительный эффект), [§ Стрессовый smoke](ISSUE_FALL.md#стрессовый-smoke--диагностика) (короткий gate-shaped stress).

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

Цель: **локализовать** вклад H1–H6 и зафиксировать метрики в [MEASUREMENTS.md](MEASUREMENTS.md) (колонка «после проработки»).

### Предусловия (все прогоны)

1. Перезагрузка ОС или ручная очистка: `taskkill /F /IM fceux64.exe`, нет orphan `python` train/benchmark (см. `preflight_bridge_sessions` в [SCRIPTS.md](SCRIPTS.md)).
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
| T2.2 | `stress_e2e_gate.py --phase ppo_spike_with_vec` | wall, ошибка | compound B4 ([ISSUE_FALL](ISSUE_FALL.md)) |
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

Заполнить колонку **«после проработки»** в [MEASUREMENTS.md](MEASUREMENTS.md).

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

---

## Связанные документы

| Документ | Содержание |
| -------- | ---------- |
| [MEASUREMENTS.md](MEASUREMENTS.md) | Сводные метрики; § деградация fps |
| [SCRIPTS.md](SCRIPTS.md) | Команды benchmark / train / stress |
| [ISSUE_FALL.md](ISSUE_FALL.md) | Инцидент gate, stress-диагностика, план R0–R5 |

---

## Чеклист выполнения (T0–T5)

Отмечать по мере выполнения. Критерий фазы — все шаги фазы `[x]`.

**Критерий закрытия плана:** T5 пройден; колонка **«после проработки»** в [MEASUREMENTS.md](MEASUREMENTS.md) заполнена; gate 2/2 wall ≥80% от gate 1/2; SB3 fps (rollout 20+) ≥4.

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

- [x] **T3.1** `train_local.sh --timesteps 50000 ...` — базовая линия зафиксирована (2026-07-13/14, ~10.5 ч); `wall_rollout` в [MEASUREMENTS.md](MEASUREMENTS.md)
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
- [x] **T5.4** колонка **«после проработки»** в [MEASUREMENTS.md](MEASUREMENTS.md) заполнена (T5.3)
- [x] **T5.✓** План T5 закрыт (H1 на gate 8×2 — открытый follow-up; длинный train H2 — улучшение)

### Remediation (после подтверждения гипотез)

Связь с [ISSUE_FALL.md](ISSUE_FALL.md) § R0–R3.

- [x] **H1** preflight + kill orphan (`R0.1`, `R0.2`) — закрыто в [5.0]
- [x] **H2** (частично) `OPENBLAS`/`torch` thread limits (`R3.1`); фаза `ppo_spike_with_vec` (`R3.2`)
- [x] **H2** (при необходимости) `gc.collect()` между rollout (`R3.3`); `n_envs` 4–6 на 16 GB — `RolloutGcCallback`, `train_local.sh --n-envs 6`, warn при `n_envs>6`
- [ ] **H3** reward/curriculum → длиннее эпизоды (ML_CONCEPT)
- [ ] **H4** периодический restart FCEUX; очистка `tmp/bridge/train_*`
- [ ] **H5** throttling `latest.zip` или async save
- [ ] **H6** документировать лимит сессии; паузы (ops)
