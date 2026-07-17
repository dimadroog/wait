# Замеры производительности train

Сводка метрик bridge IPC и end-to-end PPO. Источники: этапы **1.5–1.9** BACKLOG, `docs/SCRIPTS.md`, прогоны `scripts/benchmark_bridge.py` и `scripts/benchmark_train.py`.

**Эталон для финального прогона [5.0]:** вердикт **1.9** (2026-07-09) — без регрессии по e2e и bridge.

---

## Среда эталонных замеров

| Параметр | Значение |
| -------- | -------- |
| CPU | Intel i7-3770 |
| ОС | Windows 10 19045 |
| `frame_skip` | 4 |
| Train no-focus | `WAIT_FCEUX_NO_FOCUS=1` (с 1.2) |
| Целевые `n_envs` | 8 (с 1.3) |
| Типичный `ep_len_mean` | ≈2 (короткие эпизоды → reset storm) |
| JSON-отчёты | `tmp/bench/` (gitignored, локально) |

Команды воспроизведения — в [SCRIPTS.md](SCRIPTS.md) § IPC benchmark / E2E train benchmark.

---

## Параметры: что измеряется

| Параметр | За что отвечает | Единица | Скрипт / режим |
| -------- | ----------------- | ------- | --------------- |
| **ms/step** | Полное время одного env-step: IPC STEP + decode obs (без PPO/torch) | мс | `benchmark_bridge.py`, 1 proc |
| **ms/hot reset** | Hot reset: `LOAD_OBS` под `bridge_load_lock` + decode (без cold start процесса) | мс | `benchmark_bridge.py` |
| **env-steps/s (1 proc)** | Throughput bridge при одном FCEUX: `1000 / ms/step` | шагов env/с | `benchmark_bridge.py`, `--n-envs 1` |
| **env-steps/s (parallel)** | Агрегат N параллельных FCEUX: суммарные steps / wall-clock фазы | шагов env/с | `benchmark_bridge.py`, `--n-envs 8` |
| **reset/step** | Отношение `ms/hot reset` к `ms/step`; >1 → reset дороже step (важно при `ep_len≈2`) | безразм. | `benchmark_bridge.py` |
| **ms/cold start** | Первый `start(load_state)` + `cache_state` до готовности bridge | мс | `benchmark_bridge.py` |
| **decode obs** | Только decode кадра на Python (после 1.7 raw — ~0.3 ms) | мс | отчёт 1.7 |
| **e2e env-steps/s (wall)** | Полный PPO `learn`: все timesteps / wall-clock (cold start 8 FCEUX в rollout 1) | шагов env/с | `benchmark_train.py --mode gate` |
| **e2e env-steps/s (steady)** | То же, но только rollout'ы после `--warmup-rollouts` (без cold start) | шагов env/с | `benchmark_train.py --mode fps` |
| **e2e/bridge (wall)** | Доля e2e от bridge parallel step-only; узкое место вне raw IPC | безразм. | `benchmark_train.py` (печатает) |
| **e2e/historical (wall)** | Ускорение vs pre-1.x e2e | крат | `benchmark_train.py` (печатает) |
| **SB3 time/fps** | FPS из лога Stable-Baselines3 (`verbose=1`) | шагов env/с | `train_ppo.py` |
| **train-smoke dummy-vec** | PPO без межпроцессного IPC (не приёмка 1.9) | шагов env/с | `train_ppo.py --dummy-vec` |

**Разделение уровней:** bridge-метрики изолируют Python↔FCEUX; e2e включает PPO update, `SubprocVecEnv`, stagger старта env, reset storm. Bridge ~22 env-steps/s ≠ e2e ~5 — ожидаемо.

---

## Сводная таблица

Колонка **5.0** — для результатов финального прогона аудита. Заполнить после `benchmark_train.py` / `benchmark_bridge.py` (см. § «Добавить результаты 5.0»).

### Bridge IPC (`benchmark_bridge.py`)

Условия: `n_envs` как в заголовке подтаблицы; `frame_skip=4`; train-профиль (raw obs с 1.7).

| Параметр | pre-1.x | 1.5 (2026-07-07) | 1.6 | 1.7 raw | 1.8 v1 | 1.9 регрессия | **5.0** |
| -------- | ------- | ---------------- | --- | ------- | ------ | ------------- | ------- |
| **ms/step** `n=1` | — | 28.6 | 29.7 | 24.0 | 16.6 | — | **~27** |
| **ms/step** `n=8` | — | 27.7 | 28.0 | 13.8 | 22.4 | — | **~27** |
| **ms/hot reset** `n=1` | — | 41.5 | 32.7 | 27.2 | 16.4 | — | **~30** |
| **ms/hot reset** `n=8` | — | 43.5 | 28.8 | 14.6 | 21.7 | — | **~30** |
| **env-steps/s (1 proc)** | — | 35.0 | 33.6 | 41.7 | 60.2 | **~38** | **~37** |
| **env-steps/s (parallel)** `n=8` | — | 19.5 | 18.9 | 21.1 | 21.9 | **~22** | **~23** |
| **reset/step** `n=8` | — | 1.57 | 1.03 | 1.06 | 0.97 | — | **~1.1** |
| decode obs (1.7+) | gd ~246 KB | gd | gd | **~0.3** | ~0.3 | — | |

Примечания:

- **pre-1.x:** формального bridge-benchmark не было; протокол — `gdscreenshot` → `.gd` ~246 KB, `POLL_INTERVAL=0.01`, два IPC на hot reset.
- **1.7:** ms/step **−16%** (`n=1`) / **−50%** (`n=8`) vs 1.5.
- **1.8:** IPC v2 (inline binary obs) медленнее (+61% ms/step `n=1`); default — v1 JSON + file obs.

### End-to-end PPO train

| Параметр | pre-1.x | 1.9 gate (2026-07-09) | **5.0** (2026-07-13) |
| -------- | ------- | --------------------- | -------------------- |
| **n_envs** | 4 | 8 | 8 |
| **e2e env-steps/s (wall)** | **~0.5** | **~5.0** | **~5.8** (gate 1/2); **~2.0** (gate 2/2 подряд) |
| **e2e env-steps/s (steady)** | — | **~5.9** | **~7.1** (gate 1/2); **~2.2** (gate 2/2 подряд) |
| **SB3 time/fps** | — | 4–5 | 5 (gate 1/2); 1–2 (gate 2/2, train_ppo подряд) |
| train-smoke dummy-vec | **~1.9** | — (не приёмка) | — |
| **bridge parallel** (ref) | ~20 (оценка) | **~22** | **~23** (stress STEP-only 128) |
| **e2e/bridge (wall)** | — | **~0.21** | **~0.25** (gate 1/2) |
| **e2e/historical (wall)** | 1× | **~10×** | **~12×** (gate 1/2) |
| Стабильность 8×2048 gate | нестабильно | зелёный | **зелёный** (2× benchmark_train + train_ppo) |
| `ep_len_mean` | ≈2 | ≈2 | ≈2 |

Примечания:

- **pre-1.x ~0.5:** грубый замер до IPC-оптимизаций (4 env); зафиксирован в BACKLOG 1.3/1.5, константа `HISTORICAL_E2E_ENV_STEPS_PER_S` в `benchmark_train.py`.
- **wall vs steady:** на 2048 steps wall **занижен** из‑за stagger 8×5 с (~35 с) и cold start; для steady — `--mode fps` (8192) или `--warmup-rollouts 1`.
- **5.0 (2026-07-13):** приёмка R5 на i7-3770 / Win10. Bridge без регрессии (~23 parallel STEP-only в `stress_e2e_gate --full`). Gate `benchmark_train --mode gate` **2/2** без IPC timeout / worker crash: прогон 1 — **5.78** env-steps/s wall; прогон 2 подряд — **1.95** (накопительная нагрузка сессии, см. [ISSUE_FALL.md](ISSUE_FALL.md)). `train_ppo --timesteps 2048` — зелёный. JSON: `tmp/bench/train_e2e_r5_{1,2}/`, `tmp/smoke/stress_e2e/report.json`.

---

## Деградация fps — базовая линия (до нагрузочного тестирования)

**Статус:** зафиксировано **до** фаз T0–T5 из [ISSUE_TRAIN_FPS_DEGRADATION.md](ISSUE_TRAIN_FPS_DEGRADATION.md). После проработки — заполнить колонку **«после проработки»** и обновить статус плана.

**Среда:** i7-3770, Win10 19045, `n_envs=8`, `frame_skip=4`, `ep_len_mean≈2`, train no-focus.

### Краткий gate (накопление сессии, 2026-07-13)

| Прогон | e2e wall | e2e steady | SB3 fps | Примечание |
| ------ | -------- | ---------- | ------- | ---------- |
| `benchmark_train --mode gate` **1/2** (чистая машина) | **5.78** | **7.1** | **5** | эталон 5.0 |
| `benchmark_train --mode gate` **2/2** (сразу подряд) | **1.95** | **2.2** | **1–2** | H1: накопительный эффект |
| Bridge parallel STEP-only (stress) | **~23** | — | — | **без** деградации vs 1.9 |

### Длительный `train_ppo` (2026-07-13/14)

Команда: `./scripts/train_local.sh --timesteps 500000 --checkpoint-out checkpoints/m1_v0.zip` (фоновый shell; внешний kill на ~10.5 ч).

| Метрика | Начало (rollout 1–10) | Перелом (rollout 11–12, ~30 мин) | Конец (rollout 71, ~10.4 ч) |
| ------- | --------------------- | -------------------------------- | --------------------------- |
| SB3 `fps` (кумулятивный) | **5–6** | **4** | **1** |
| Wall на rollout* | **~150 с** | **~280 → ~650 с** | **~600–700 с** |
| `total_timesteps` | 1 280 → 10 496 | 11 520 → 12 544 | **72 960** |
| IPC timeout / crash в логе | нет | нет | нет |
| Checkpoint сохранён | — | — | **нет** (жёсткий kill) |

\*разница `time_elapsed` между соседними строками `iterations` в логе SB3.

**Вывод (базовая линия):** bridge стабилен (~23 env-steps/s); e2e падает **~3–6×** на длинной сессии при том же `ep_len≈2`. Резкий скачок wall/rollout на **~30-й минуте** — кандидат на порог RAM/swap (H2).

### Целевые показатели «после проработки» (заполнить после T5)

| Метрика | Базовая линия | После проработки | Δ |
| ------- | ------------- | ---------------- | - |
| gate 1/2 wall env-steps/s | 5.78 | **6.26** (T1.4) | +8% |
| gate 2/2 wall env-steps/s | 1.95 | **1.52** (T5.2, 2026-07-14) | **40%** от 1/2 — H1 не закрыта на gate |
| train rollout 10 wall | ~650 с | **273 с** (T5.3, n=6) | **−58%** |
| train rollout 20 wall | *нет данных* | **99 с** (T5.3) | стабильно vs базовая конец |
| SB3 fps (rollout 20+, кумулятивный) | ~1–2 | **2–3** (T5.3) | цель ≥4 **не достигнута** |
| Bridge parallel (контроль) | ~23 | **26.00** (T5.1) | без регрессии |

### H2 remediation: smoke `n_envs` 4 vs 6 (2026-07-14)

**Цель:** выбрать default для длинного train на 16 GB после remediation H2 (`RolloutGcCallback`, `train_local.sh --n-envs 6`).

**Команда (оба прогона):**

```bash
./.venv/Scripts/python.exe src/train/train_ppo.py --smoke --timesteps 4096 --no-bc --no-resume \
  --smoke-session h2_cmp_n{N} --n-envs {4|6}
```

Между прогонами — `preflight_bridge_sessions` (без reboot). `n_envs=4` шёл **сразу после** `n_envs=6` (возможен вклад H1 на втором прогоне).

| Метрика | `n_envs=6` | `n_envs=4` | Δ (6 vs 4) |
| ------- | ---------- | ---------- | ---------- |
| FCEUX процессов | 6 | 4 | +50% RAM footprint |
| Wall (с) | **588** | **929** | **−37%** времени |
| Env-steps (факт) | 4608* | 4096 | *SB3 завершил полный rollout |
| **env-steps/s (wall)** | **7.8** | **4.4** | **+77%** |
| **env-steps/s (steady)**† | **8.0** | **4.5** | **+78%** |
| SB3 `fps` (финальный) | **7** | **4** | +75% |
| Rollout 1 wall (с) | 108 | 124 | cold start |
| Rollout 2–N wall (с, среднее) | **~96** | **~115** | стабильнее у n=6 |
| IPC timeout / crash | нет | нет | — |
| `ep_len_mean` | 2 | 2 | — |

†steady: rollout'ы после 1-го; `env_steps / wall` без cold start первого rollout.

**Контекст:** ранний прогон T2.4 (`n_envs=4`, 4096 steps, без smoke) — wall **457 s**, fps **6–9**; сегодняшний `n=4` медленнее из‑за накопительной нагрузки сессии (H1) после `n=6`.

**Вердикт:** для 16 GB RAM предпочтителен **`n_envs=6`** — почти **×2 throughput** vs `n=4` при приемлемой RAM-нагрузке (6 FCEUX + PPO). `n_envs=4` — запасной режим при устойчивом OOM/swap или жёстком лимите RAM; на throughput проигрывает. Gate/benchmark-приёмка остаётся на **`n_envs=8`**; длинный train — **`train_local.sh`** (default `--n-envs 6`).

### T5.3 длинный train после H2 remediation (2026-07-14)

**Команда:** `./scripts/train_local.sh --timesteps 20000 --save-every 5000 --checkpoint-out checkpoints/m1_v0_fps_t5.zip` (`n_envs=6`, `RolloutGcCallback` on).

| Метрика | Базовая линия (n=8) | T5.3 (n=6 + H2) |
| ------- | ------------------- | --------------- |
| Rollout'ов | 71 (kill ~10.5 ч) | **27** (complete) |
| Wall total | ~10.5 ч | **6658 с** (~1.85 ч) |
| `wall_rollout` rollout 1 | ~150 с | **382 с** |
| `wall_rollout` rollout 10 | **~650 с** | **273 с** |
| `wall_rollout` rollout 20+ | **~600–700 с** | **~93–100 с** (стабильно) |
| SB3 fps (rollout 20+) | ~1–2 | **2–3** |
| IPC timeout / crash | нет | retry only, **нет** crash |
| Checkpoint | нет (kill) | **m1_v0_fps_t5.zip** |

**Вывод T5.3:** remediation H2 (`n_envs=6` + gc) **снимает деградацию wall/rollout** на длинной сессии vs базовая линия n=8; кумулятивный SB3 fps **2–3** (цель ≥4 не достигнута). Gate H1 (2× gate n=8 подряд) остаётся отдельным follow-up — между gate нужен preflight/reboot.

Лог: `tmp/bench/t5_3_train.log`.

### R6 dual train+measure (заполнить после прогона)

План и команды: [ISSUE_TRAIN_FPS_DEGRADATION.md § R6](ISSUE_TRAIN_FPS_DEGRADATION.md#раунд-r6--dual-trainmeasure-2026-07-17).

| Метрика | R6.1 n=4 | R6.1 n=6 | R6.1 n=8 | R6.2 long n=6 |
| ------- | -------- | -------- | -------- | ------------- |
| env-steps/s (steady) | | | | |
| wall_late/early | | | | |
| avail_phys_mb min | | | | |
| SB3 fps (late) | | | | |
| checkpoint | smoke tmp | smoke tmp | smoke tmp | `m1_v0_n6.zip` |

**Вердикт R6:** _TBD_

---

## Добавить результаты 5.0

1. `cleanup_bridge_sessions` — нет зависших `fceux64.exe`.
2. Bridge:

   ```bash
   ./.venv/Scripts/python.exe scripts/benchmark_bridge.py --n-envs 8
   ./.venv/Scripts/python.exe scripts/benchmark_bridge.py --n-envs 1
   ```

3. E2E gate + steady:

   ```bash
   ./.venv/Scripts/python.exe scripts/benchmark_train.py --mode gate
   ./.venv/Scripts/python.exe scripts/benchmark_train.py --mode fps
   ```

4. Перенести значения из stdout (или JSON) в колонку **5.0** выше; указать дату и отличия среды, если железо/ОС изменились.
5. JSON: `tmp/bench/<session>/train_report.json`, `tmp/bench/bridge_baseline/baseline_report.json`.
6. После прогона: `cleanup_artifact_quarantine("bench")` (см. DESIGN § Гигиена артефактов).

---

## Связанные документы

| Документ | Содержание |
| -------- | ---------- |
| [SCRIPTS.md](SCRIPTS.md) | Команды benchmark, аргументы CLI |
| [BACKLOG.md](BACKLOG.md) | Этапы 1.5–1.9, вердикты, критерий 5.0 |
| [DESIGN.md](DESIGN.md) | `tmp/bench/`, карантин артефактов |
| [ISSUE_TRAIN_FPS_DEGRADATION.md](ISSUE_TRAIN_FPS_DEGRADATION.md) | План нагрузочного тестирования fps, гипотезы H1–H6 |
