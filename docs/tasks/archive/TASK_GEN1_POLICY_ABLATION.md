# TASK_GEN1_POLICY_ABLATION — однофакторный разбор noop-политики gen1

**Статус:** done (закрыто 2026-07-22)  
**Итог:** ablation H0–H5 измерен; канон routes = H3; CLI `summarize_inference_actions` для `noop_frac`.  
**Приоритет:** high  
**Ветка:** `task/gen1-policy-ablation` — проработку этой задачи выполнять только в этой ветке.  
**Зависит от:** [TRAIN_ANALYSIS.md](../../TRAIN_ANALYSIS.md) (чтение лога); исходный `models/gen0.zip` как контроль  
**Файлы:** `docs/TRAIN_ANALYSIS.md`, `docs/GAME_RUSHN_ATTACK.md` §2 (награды/CP), `games/rushn_attack/missions/m1/config/routes.yaml`, `games/rushn_attack/env_config.yaml`, `config/achievements.yaml` (только если понадобится метка), `src/train/train_ppo.py` / `scripts/train_local.sh` (CLI as-is), `src/stream/run_inference.py`, `src/inference_action_stats.py`, `scripts/summarize_inference_actions.py`  
**Контекст в чат:** этот файл + [TRAIN_ANALYSIS.md](../../TRAIN_ANALYSIS.md) + [GLOSSARY.md](../../GLOSSARY.md) (BC, поколение, rollout) + `routes.yaml`

### Цель

Понять **какой один фактор** увёл `gen1` в политику «почти всегда пустое действие / стояние», не меняя всё сразу.  
Метод: серия **минимальных** прогонов обучения, в каждом меняется **ровно один** параметр относительно зафиксированного контроля; сравнение по консоли ([TRAIN_ANALYSIS](../../TRAIN_ANALYSIS.md)) и короткому inference (доля непустых действий, не только `max_checkpoint`).  
Да: такой дизайн улучшает понимание «что именно сработало»; нет — если смешать правки или разные бюджеты timesteps без контроля.

### Бюджет времени одного прогона (ориентир ±2 ч)

Железо: CPU train, `train_local.sh` (`n_envs=6`), типичный порядок **~4–8 env-step/s**.

| Статья | Оценка |
| ------ | ------ |
| Короткий PPO-добор | **~30 000** новых env-step ≈ **1–2.5 ч** wall (при 4–8 step/s) |
| BC (`--bc-epochs` 1…5) | **~5–20 мин** (не доминирует) |
| Inference 5–8 эпизодов + разбор лога | **~0.5–1 ч** |
| **Итого на одну гипотезу** | **~3±2 ч** (от ~1.5 ч на быстрой машине/коротком стопе до ~5 ч при просадке fps) |

Полный ряд H0→H5 без пропусков: ориентир **~18±6 ч** чистого прогона (не календарь «сутки», а сумма wall-clock сессий). Допускается стоп гипотезы раньше по [правилу остановки](../../TRAIN_ANALYSIS.md#практическое-правило-остановки-политика).

Фиксировать в заметках задачи: точная команда, `model-out`, `num_timesteps` до/после, 3 среза таблицы (начало/середина/конец), `noop_frac` inference.

### Контроль и метрики сравнения (одинаковы для всех H)

**Контрольный рецепт коллапса (зафиксировать один раз как H0):**  
`gen0` (`num_timesteps=715284`) → `--bc-epochs 5` → PPO добор до **`--timesteps 745284`** (+30k) → `models/ablation/h0_bc5.zip` (не затирать `gen0`/`gen1`).

**Метрики (минимум):**

| Метрика | Где | Успех vs провал |
| ------- | --- | ---------------- |
| `entropy_loss`, `approx_kl`, `clip_fraction` | консоль train | живые vs схлопнутые по TRAIN_ANALYSIS |
| `ep_rew_mean` / `ep_len_mean` | консоль | dynamика vs залипание |
| `noop_frac` | inference inputs / подсчёт пустых `action` | **главный** поведенческий критерий (цель: заметно ниже, чем у noop-gen1 ≈ ~1.0) |
| `max_checkpoint` | attempts | вторично; не единственный критерий |

Скрипт сводки (после стабилизации протокола): ядро считает нейтральные поля из jsonl; игровые пороги CP — только в плагине/`routes`, без `if game_id` в `src/`.

### Гипотезы (от более производительной к менее)

Менять **только** указанный рычаг; остальное как у контроля H0 (кроме H1, где BC выключен намеренно).

| ID | Одна правка | Зачем (ожидание) | Ожидаемое wall |
| -- | ----------- | ---------------- | -------------- |
| **H0** | Воспроизведение: `gen0` + `--bc-epochs 5` + PPO +30k | База «коллапс повторяется быстро» | ~3±2 ч |
| **H1** | То же, но **`--bc-epochs 0` / `--no-bc`** | Если noop нет — главный виновник BC-затирание `gen0` | ~3±2 ч |
| **H2** | `--bc-epochs 1` (не 5) | Сила BC, не факт наличия BC | ~3±2 ч |
| **H3** | Правка **только** награды/триггеров CP (двойной бонус на `room 0x00` / старт), рецепт как H0 | Если noop уходит — закрепление стоянием через награду | ~3±2 ч + время на аккуратную правку YAML плагина |
| **H4** | BC по демо **без** сегментов/семплов с доминированием пустого действия; epochs как H0 | Частота класса «пусто» в BC | ~3±2 ч + фильтр демо |
| **H5** | Новая сеть (без `--model-in gen0`) + BC как H0 + PPO +30k | Взаимодействие «тёплый gen0 + BC» | ~3±2 ч (с нуля может быть слабее по игре — смотреть noop_frac, не WR) |

Не смешивать H3+H1 в одном прогоне. H5 не интерпретировать как «лучшая модель сезона» — только фактор.

### Протокол одного прогона (за раз)

Работать **строго по одной гипотезе за раз** на стороне оператора: одна train-команда из списка → дождаться конца (или раннего стопа) → следующая H. Inference и заполнение таблицы — **после серии**, агентом по сохранённым `.log` / `.zip` / sidecar.

**Контроль `gen0` (зафиксировано 2026-07-22):**

| Поле | Значение |
| ---- | -------- |
| Путь | `games/rushn_attack/missions/m1/models/gen0.zip` |
| `num_timesteps` | **715284** (`gen0.train.json`) |
| Бюджет добора | **+30000** env-step |
| Абсолютный `--timesteps` для H0–H4 (load gen0) | **745284** (= 715284 + 30000) |
| Для H5 (новая сеть) | `--timesteps 30000` (счётчик с нуля) |

Важно: `train_ppo` считает `remaining = target − model.num_timesteps`. Флаг `--timesteps 30000` при `--model-in gen0` даст «target already reached» и **нулевой** PPO-добор. Не путать «бюджет +30k» с абсолютной целью CLI.

**Артефакты:** только `models/ablation/hN_….zip` (+ sidecar рядом). Не трогать `gen0.zip` / `gen1.zip`. Каталог: `games/rushn_attack/missions/m1/models/ablation/`. Логи train: `tmp/bench/ablation_hN_train.log`.

**Разделение ролей:** оператор гоняет **только train** по списку ниже (copy/paste). После серии прогонов агент по логам + sidecar заполняет таблицу, сам снимает inference / `noop_frac`, пишет выводы. Inference оператору запускать не обязательно.

Ранний стоп train по [правилу остановки](../../TRAIN_ANALYSIS.md#практическое-правило-остановки-политика) допускается (Ctrl+C → атомарный save); в чат потом: какая H и что остановило.

### Команды train (copy/paste, с `tee`)

Корень репозитория `d:/wait` (или эквивалент). Ветка: `task/gen1-policy-ablation`. Один прогон за раз; следующую команду — после выхода предыдущей (или после явного раннего стопа).

**0) Один раз — каталоги**

```bash
mkdir -p tmp/bench games/rushn_attack/missions/m1/models/ablation
```

**H0 — контроль коллапса** (`gen0` + BC 5 + PPO +30k)

```bash
./scripts/train_local.sh \
  --model-in models/gen0.zip \
  --model-out models/ablation/h0_bc5.zip \
  --no-resume \
  --bc-epochs 5 \
  --timesteps 745284 \
  --save-every 30000 \
  2>&1 | tee tmp/bench/ablation_h0_train.log
```

**H1 — без BC** (тот же load/бюджет; рычаг: `--no-bc`)

```bash
./scripts/train_local.sh \
  --model-in models/gen0.zip \
  --model-out models/ablation/h1_no_bc.zip \
  --no-resume \
  --no-bc \
  --timesteps 745284 \
  --save-every 30000 \
  2>&1 | tee tmp/bench/ablation_h1_train.log
```

**H2 — слабый BC** (рычаг: `--bc-epochs 1`)

```bash
./scripts/train_local.sh \
  --model-in models/gen0.zip \
  --model-out models/ablation/h2_bc1.zip \
  --no-resume \
  --bc-epochs 1 \
  --timesteps 745284 \
  --save-every 30000 \
  2>&1 | tee tmp/bench/ablation_h2_train.log
```

**H3 — правка награды/CP** (рецепт как H0; рычаг routes плагина)

**Готово к запуску (2026-07-22).** Правка в `config/routes.yaml` (оригинал для отката: `config/routes.pre_h3.yaml`):

1. Убран CP0 `start` (`room 0x00`) — больше нет бесплатного +100 при каждом reset за стояние на старте.
2. У CP4 `late_mission` добавлено `requires_checkpoint: 3` — `room 0x00` + `min_y≥60` не даёт прыжок на CP4, пока не взят mid_mission (`0x12`).

В ядре: нейтральное поле триггера `requires_checkpoint` в `CheckpointRewardWrapper` (не `if game_id`). После H3 **вернуть** routes: `cp config/routes.pre_h3.yaml config/routes.yaml` (из каталога миссии) перед H4/H5.

```bash
./scripts/train_local.sh \
  --model-in models/gen0.zip \
  --model-out models/ablation/h3_reward_cp.zip \
  --no-resume \
  --bc-epochs 5 \
  --timesteps 745284 \
  --save-every 30000 \
  2>&1 | tee tmp/bench/ablation_h3_train.log
```

**H4 — BC без доминирования пустого действия** (epochs как H0; рычаг состав демо)

**Готово к запуску (2026-07-22).** `routes.yaml` откатан к `routes.pre_h3.yaml` (как у H0).  
Файл: `reference/demos_for_bc_ablation/h4_filtered.npz` (781 семпл, `noop_frac=0`):

- выброшены сегменты с noop ≥ 50%: `seg_001`, `seg_005` (оба 100% пусто);
- в оставшихся (`seg_002`–`004`) убраны семплы с пустым действием;
- meta `prefer_embedded_actions: true` — `bc_pretrain` читает `actions` из npz.

```bash
./scripts/train_local.sh \
  --model-in models/gen0.zip \
  --model-out models/ablation/h4_bc_filtered.zip \
  --no-resume \
  --bc-epochs 5 \
  --bc-demo reference/demos_for_bc_ablation/h4_filtered.npz \
  --timesteps 745284 \
  --save-every 30000 \
  2>&1 | tee tmp/bench/ablation_h4_train.log
```

**H5 — с нуля** (без `--model-in gen0`; BC 5 + PPO 30k с чистого счётчика)

```bash
./scripts/train_local.sh \
  --model-out models/ablation/h5_scratch_bc5.zip \
  --no-resume \
  --bc-epochs 5 \
  --timesteps 30000 \
  --save-every 30000 \
  2>&1 | tee tmp/bench/ablation_h5_train.log
```

Ожидаемые файлы после серии: `models/ablation/h{0..5}_*.zip` (+ `.train.json`), `tmp/bench/ablation_hN_train.log`. Когда всё готово — написать в чат; агент снимет inference и заполнит сводку.

**Таблица сводки (после train + inference 4×200 stochastic, `tmp/bench/ablation_inference/noop_frac.json`):**

| ID | model-out | ts до → после | entropy (конец) | approx_kl / clip (конец) | noop_frac | вердикт |
| -- | --------- | ------------- | --------------- | ------------------------ | --------- | ------- |
| H0 | `h0_bc5.zip` | 715284 → +30k (счётчик 30720) | −0.046 | ~3e-4 / 0.003 | **0.023** | Репро **пустого** noop **нет**; залипание `ep_rew=460`/`ep_len=11` + max_cp=4 → фарм CP на `0x00` |
| H1 | `h1_no_bc.zip` | то же | **−0.004** | **0 / 0** | **1.000** | Без BC — полный noop; BC **не** главный виновник пустых действий |
| H2 | `h2_bc1.zip` | то же | **−0.002** | **0 / 0** | **0.998** | Слабый BC ≈ как без BC по noop |
| H3 | `h3_reward_cp.zip` | то же | **−1.25** (живая) | ~2e-4 / 0 | **0.403** | Правка CP убрала `ep_rew=460` (стало ≈−40); энтропия жива; noop заметно ниже H1/H2/H4/H5 |
| H4 | `h4_bc_filtered.zip` | то же | **−0.001** | **0 / 0** | **1.000** | Фильтр пустых в демо **не** спас от noop |
| H5 | `h5_scratch_bc5.zip` | 0 → 30720 | **−0.009** | ~0 / 0 | **0.994** | С нуля + BC5 → снова noop; «тёплый gen0» сам по себе не единственный фактор пустоты |

Inference: 4 эпизода × до 200 шагов, stochastic; у всех `max_checkpoint_max=4` на **текущем** (откатанном) `routes.yaml` — метрика CP при eval не изолирует H3-награду.

### Чеклист сессии

- [x] Зафиксировать протокол: бюджет +30k, путь артефактов `models/ablation/`, таблица метрик в этом файле (заметки)
- [x] H0: прогон + inference; высокий `noop_frac` **не** подтверждён (0.02) — репро именно пустого noop не удалось; подтверждено залипание награды/длины
- [x] H1: без BC → noop_frac=1.0
- [x] H2: bc-epochs=1 → noop_frac≈1.0
- [x] H3: правка routes → энтропия жива, noop_frac≈0.40
- [x] H4: фильтр BC-демо → noop_frac=1.0
- [x] H5: без gen0 → noop_frac≈0.99
- [x] Сводка: главный вклад + рекомендация для gen1 (ниже)
- [x] Тонкий скрипт сравнения inputs/attempts: `scripts/summarize_inference_actions.py` → `src/inference_action_stats.py`
- [x] DoD → archive по [TASK_BLANK](../TASK_BLANK.md)
- [x] Follow-through: канон H3 в `routes.yaml`; `routes.pre_h3.yaml` как снимок; GAME §2 обновлён

### Follow-through done (2026-07-22)

- Канон маршрута миссии = H3 (нет CP0 `start` на `0x00`; `late_mission` с `requires_checkpoint: 3`) — в `config/routes.yaml`; снимок до правки: `config/routes.pre_h3.yaml` (не боевой путь).
- Ядро: `requires_checkpoint`, `prefer_embedded_actions`, CLI `summarize_inference_actions` (+ unit-тесты).
- Артефакт H4: `reference/demos_for_bc_ablation/` (не дефолт BC).
- **Рекомендация боевого gen1** (держать здесь, не в GAME): тёплый `gen0` + BC ≥ 1…5 эпох + PPO на H3-routes; смотреть `noop_frac` (`summarize_inference_actions`) и залипание `ep_rew` / `ep_len` в train ([TRAIN_ANALYSIS](../../TRAIN_ANALYSIS.md)).

### Гигиена артефактов (2026-07-23)

- Локальный каталог `games/rushn_attack/missions/m1/models/ablation/` (`h0`…`h5` zip + sidecar) **удалён** — не восстанавливать в git / models миссии.
- Журнал прогонов, таблица `noop_frac`, copy/paste train-команды и выводы — **только в этом TASK** (ниже). Сырые train-логи при наличии: `tmp/bench/ablation_hN_train.log` (gitignore).
- Из [GAME_RUSHN_ATTACK §2](../../GAME_RUSHN_ATTACK.md#2-награды-и-чекпоинты-m1) убран развёрнутый ablation/gen1-контекст; в GAME остаётся фактический канон routes + ссылка сюда.

### Критерий готовности (DoD)

- [x] Для H0–H5 есть команда, артефакт модели, выписка из логов, `noop_frac`
- [x] В заметках назван **главный** фактор (и оговорка по H0)
- [x] Рекомендация для боевого `gen1` сформулирована одним абзацем
- [x] Нет смешения нескольких правок в одном прогоне; `gen0.zip` не перезаписан

### Не делать (антискоуп)

- Менять сразу BC + routes + демо в одном train
- Длинные прогоны на 1–2M «на всякий случай» вместо короткого бюджета
- Новый код ради кода до стабилизации протокола измерений
- Стрим / playlist / OBS
- Списывать `gen0` или продакшен-`gen1` без копии в `ablation/`

### Заметки / гипотезы

Контекст исходного провала: `gen1` после BC+PPO → почти всегда `action=""`; консоль по TRAIN_ANALYSIS уже показывала схлопывание; визуальный playlist подтвердил.

Порядок H0→H5 = «сначала отделить BC от остального, потом силу BC, потом награду, потом состав демо, потом необходимость gen0».

**Сессия 2026-07-22 — протокол:** ветка `task/gen1-policy-ablation`; `gen0` = 715284 ts; цель добора H0–H4 = 745284; артефакты только в `models/ablation/`; логи — `tmp/bench/ablation_hN_train.log`. Оператор: train по copy/paste-списку. Агент: после серии — разбор логов, inference, таблица, выводы.

**Статус прогонов:** H0–H5 train **complete** (все `saved (complete)`, sidecar `num_timesteps=30720`). Inference noop_frac снят 2026-07-22.

#### Итог ablation

**Главный фактор по пустым действиям (`noop_frac`):** короткий PPO-добор **без** достаточного BC (H1) или с слабым/отфильтрованным BC на «плохом» режиме (H2/H4/H5) уводит в noop≈1. Гипотеза «BC 5 эпох затирает gen0 в пустоту» **опровергнута**: контроль H0 как раз почти без пустых действий (`noop_frac≈0.02`), а выключение BC (H1) даёт полный noop.

**Второй независимый фактор (награда/CP):** ложный прогресс на `room 0x00` (CP0 + CP4 без `requires_checkpoint`) даёт залипание `ep_rew_mean≈460` / `ep_len_mean≈11` и `max_checkpoint=4` без реальной игры. H3 (убрать платный старт + `requires_checkpoint: 3` у late) единственный держит **живую энтропию** (~−1.25) и режет noop до ~0.40 при том же BC5+gen0.

**H0 не воспроизвёл** исходный визуальный «всегда `action=""`» за +30k — воспроизвёл **дегенерацию через фарм CP**, не через пустую кнопку. Имеет смысл не смешивать эти два симптома.

**Рекомендация для боевого gen1:** оставить тёплый `gen0` и умеренный/полный BC (не `--no-bc` и не полагаться на «BC виноват»); **обязательно** закрепить правку routes как в H3 (нет платного CP0 на старте; late `0x00` только после mid_mission); не ждать спасения от фильтра noop в демо (H4 не помог). Новый прогон gen1 = gen0 + BC≥1…5 + PPO на **исправленных** routes, смотреть и `noop_frac`, и залипание `ep_rew`/`ep_len`.

#### H0–H5 (срезы train — кратко)

Сырые логи: `tmp/bench/ablation_hN_train.log`. У H0/H1/H2/H4 `ep_rew_mean`/`ep_len_mean` бит-в-бит 460/11 почти весь прогон; у H3 — −40.1/11 (нет бесплатного CP-бонуса).
