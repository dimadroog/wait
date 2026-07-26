# TASK_POLICY_SEPARATION — разделение политик (Multi-head; пилот: title / cutscene)

**Статус:** done  
**Закрыто:** 2026-07-26 — Multi-head в ядре; пилот RnA title/intro/gameplay; `head_save_states` + один канон `cp_gameplay0`; isolation/coverage пилоты PASS; cleanup legacy inference/compat.  
**Приоритет:** high  
**Ветка:** `task/policy-separation`.  
**Зависит от:** конец попытки RnA по game-over-freeze ([TASK_STOP_TITLE_ATTRACT](TASK_STOP_TITLE_ATTRACT.md), done); `start` уже в `games/rushn_attack/env_config.yaml` actions (Discrete меняется → нужен retrain).  
**Файлы (ориентиры):** `src/train/multi_head_policy.py`, `src/train/phase_heads.py`, `src/train/train_ppo.py`, `src/stream/run_inference.py`, `src/playthrough_build.py`, `games/rushn_attack/env/`, `games/rushn_attack/env_config.yaml`, `games/rushn_attack/etalon_build.yaml`, `missions/*/config/playthrough_manifest.yaml`, `docs/DESIGN.md`, `docs/GLOSSARY.md`  
**Контекст в чат:** этот файл + [DESIGN.md](../../DESIGN.md) (Pluggable Core / слоты) + [GAME_RUSHN_ATTACK.md](../../GAME_RUSHN_ATTACK.md) § действия / конец эпизода

Каркас: [TASK_BLANK.md](../TASK_BLANK.md)

### Цель

Ввести в каркас **разделение политик** как **Multi-head**: одна сеть / один `models/genN.zip`, shared backbone и отдельные головы с явной маршрутизацией по [фазе экрана](../../GLOSSARY.md#фаза-экрана-phase_id) (`phase_id` → `head_id`). Геймплейная голова не должна искажаться опытом title / intro / cutscene; позже — боссы и иные режимы на том же API.

Первый практический срез — **начало Rush'n Attack**: голова `intro` (title + стартовая cutscene, в т.ч. `start`) и голова `gameplay` после входа в уровень. Это пилот механизма платформы, не одноразовый хак под одну игру.

### Почему не «скрипт на фазу»

Скриптовый remap действий на title/attract **не** изолирует искажение [PPO](../../GLOSSARY.md#ppo): в буфер rollout всё равно попадает чужой режим, градиенты смешивают несовместимые задачи. Разделение политик (головы + маскированный policy-loss) — выбранный путь проекта.

### Почему не несколько zip + router

Курс **Multi-head** согласован с циклом жизни модели и эфира: поколение = один [`genN.zip`](../../GLOSSARY.md#поколение-модели-genn) ([ML_CONCEPT](../../ML_CONCEPT.md), [STREAMING_CONCEPT](../../STREAMING_CONCEPT.md)). Несколько SB3 zip + `bundle.yaml` — **антискоуп** этой задачи (операционный коммутатор файлов вместо одной модели поколения).

### Архитектурные рамки ([DESIGN](../../DESIGN.md))

| Слой | Что принадлежит |
| ---- | --------------- |
| **Ядро** | custom SB3 multi-head policy; phase→head; train/inference без `if game_id` |
| **Плагин** | детектор фазы (YAML + hooks), `phase_to_head`, опц. action mask по голове |

Не копировать `src/train/` под игру.

### Чеклист сессии

- [x] Зафиксировать термины в [GLOSSARY](../../GLOSSARY.md) (разделение политик / фаза экрана / `phase_id`) и слот в [DESIGN](../../DESIGN.md) — **формулировки под Multi-head**
- [x] Постановка v1: Multi-head, один `genN.zip`, `info["phase_id"]`, изоляция policy-loss
- [x] Детектор фаз RnA (только плагин): title / intro / gameplay
- [x] Ядро: multi-head SB3 policy + phase→head + predict/train hooks (`multi_head_policy`, `phase_heads`, `phase_aware_ppo`, hook в `train_ppo`)
- [x] Inference: один zip, выбор головы; step-лог: `phase_id` + `head_id` (legacy CnnPolicy zip — fallback)
- [x] Unit: phase→head, mask intro, batch heads; screen_phase RnA
- [x] Обновить [SCRIPTS](../../SCRIPTS.md) / [GAME_RUSHN_ATTACK](../../GAME_RUSHN_ATTACK.md) при смене CLI или контракта
- [x] Проработка: именование save states относительно `head_id` (см. §5 ниже)
- [x] Проработка кода: workflow + что автоматизирует ядро (см. §6 ниже)
- [x] Якоря кадров m1 (`clear.fm2`): title/intro0–1/gameplay0..4/bossfight0 → `head_save_states` в манифесте
- [x] Реализовать §5–§6 (пилот): имена `cp_<head><i>`, один канон train/inference, GUID не в каноне; `build_playthrough --states-only`
- [x] Минимальный train-пилот Multi-head + isolation (smoke, `cp_title0`, 128–256 steps)
- [x] Более длинный пилот: title→intro→gameplay на learn (`cp_title0`, 16k steps, coverage+isolation)
- [x] Запись уроков пилотов → заметки ниже

### Постановка v1 (2026-07-25, Multi-head)

Зафиксированные решения. Код обязан следовать этому контракту; смена — явная правка этой секции.

#### 1. Сигнал фазы из env

| Решение | Выбор v1 |
| ------- | -------- |
| Канал | **`info["phase_id"]`** (строка) на каждом `reset` и `step` |
| Observation | **не трогать** — стек `(4, 84, 84)`; без aux в obs |
| Кто пишет | плагин (детектор); ядро только читает |
| Нет / unknown `phase_id` | `default_head` из манифеста голов (+ warning) |
| VecEnv | `infos[i]["phase_id"]`; выбор головы per-env / per-sample |

Пилот RnA:

| `phase_id` | `head_id` |
| ---------- | --------- |
| `title` | `title` |
| `intro` | `intro` |
| `gameplay` | `gameplay` |
| `bossfight` | `bossfight` (детектор — later) |

#### 2. Формат артефактов `models/`

**Выбрано: одна SB3 `PPO` zip с Multi-head policy** (shared CNN + головы).

| Режим | Раскладка |
| ----- | --------- |
| Одна голова / legacy | `models/genN.zip` с обычным `CnnPolicy` — как сейчас |
| Multi-head | тот же путь `models/genN.zip`; внутри — custom policy; маппинг голов — YAML плагина (не каталог с несколькими zip) |

Пример манифеста в `env_config.yaml` (или рядом в плагине):

```yaml
policy_heads:
  default_head: gameplay
  heads: [title, intro, gameplay, bossfight]
  phase_to_head:
    title: title
    intro: intro
    gameplay: gameplay
    bossfight: bossfight
  action_masks:
    title: ["", "start"]
    intro: [""]
```

- `model_version` / пул логов: stem = `genN` от `genN.zip`.
- CLI: `--model genN.zip` (каталог `genN/` + multi-zip **не** поддерживается).
- **Не в v1:** несколько PPO zip + router; options/hierarchical.

#### 3. Поведение reset / switch

1. После `reset` / `step` читается `phase_id` → `phase_to_head` → активная голова.
2. `predict`: forward shared backbone → logits активной головы (+ action mask).
3. Смена фазы: со следующего решения — другая голова; без soft-reset RNN (CnnPolicy).
4. Train: один `PPO.learn`; **policy-loss** только по сэмплам активной головы (`phase_id` из infos). Value — shared (v1).
5. Метрика изоляции: доля / счётчик обновлений gameplay-головы на шагах `phase_id ∈ {title,intro}` = 0 (или явный лог).

**Inference:** один `PPO.load`; лог `phase_id`, `head_id`.

#### 4. Границы API ядра

- `src/train/multi_head_policy.py` — SB3 policy class.
- `src/train/phase_heads.py` — загрузка манифеста, `head_id_for_phase`, `predict_with_phase`.
- Без импорта `games.rushn_attack` и без констант комнат RnA.

Плагин: `info["phase_id"]`, YAML `policy_heads` (+ masks).

#### 5. Именование save states относительно голов (проработка 2026-07-26)

**Проблема:** имена вроде `cp0` / `etalon_start` / `inference_cp0` не говорят, для какой головы снимок; два «геймплей-старта» (`cp0` vs `inference_cp0`) уже давали рассинхрон train ↔ inference (title vs gameplay).

**Выбрано: имя = голова + индекс прогресса внутри зоны головы.**

| Имя | Голова | Смысл |
| --- | ------ | ----- |
| `cp_title0` | `title` | title screen |
| `cp_intro0` | `intro` | стартовый cutscene |
| `cp_gameplay0` | `gameplay` | старт уровня (канон train **и** inference reset) |
| `cp_gameplay1`… | `gameplay` | прогресс дальше по миссии |
| `cp_bossfight0` | `bossfight` | старт зоны босса |

Формат файла: `save_states/cp_<head_id><index>.fc0` (например `cp_gameplay0.fc0`). Идентификаторы голов — из манифеста `policy_heads.heads` плагина, **не** захардкожены в ядре.

**Контракт путей (YAML миссии / etalon build, не `if` в ядре):**

```yaml
# m1 / clear.fm2 — в playthrough_manifest.yaml; .fc0 пишет build_playthrough --states-only
head_save_states:
  title: [{id: cp_title0, frame: 20, label: title_screen}]
  intro:
    - {id: cp_intro0, frame: 358, phase_end_frame: 1191, label: mission_start_intro}
    - {id: cp_intro1, frame: 5492, phase_end_frame: 5909, label: post_mission_intro}
  gameplay:
    - {id: cp_gameplay0, frame: 1243, label: level_start}
    - {id: cp_gameplay1, frame: 1506, label: after_second_ladder}
    - {id: cp_gameplay2, frame: 2255, label: ladders_done_mines_start}
    - {id: cp_gameplay3, frame: 3237, label: after_red_enemy_ground}
    - {id: cp_gameplay4, frame: 3672, label: after_single_mine}
  bossfight:
    - {id: cp_bossfight0, frame: 4330, label: mission1_boss}
```

Ядро/CLI выбирают снимок из манифеста; плагин задаёт список и кадры сборки.

**Один канон на точку прогресса:**

| Решение | Выбор |
| ------- | ----- |
| Train default (gameplay) | тот же файл, что inference reset: `cp_gameplay0` |
| Отдельный `inference_cp*` на диске миссии | **нет** |
| GUID для FM2 embed | только staging / строка `savestate` клипа |
| Intro-пилот | `--save-state …/cp_intro0.fc0` или `cp_title0` |

**Не путать оси:**

| Ось | Примеры | Зачем |
| --- | ------- | ----- |
| `phase_id` | `title`, `intro`, `gameplay` | сигнал экрана из env |
| `head_id` | `title`, `intro`, `gameplay` | какая голова сети |
| имя save state | `cp_intro0`, `cp_gameplay0` | точка сброса эмулятора |

Сборка: `save_state_plan` **требует** `head_save_states` (без fallback `cp0` / `etalon_start` / `inference_cp*`).

#### 6. Workflow и автоматизация ядра (2026-07-26; cleanup 2026-07-26)

**Порядок работы:**

1. **Человек / плагин** — `policy_heads`, `screen_phases`, якоря `head_save_states`.
2. **Разведка эталона** — кадры границ (вручную + опц. эвристика `etalon_build`).
3. **Сборка** — `build_playthrough` / `--states-only` → `cp_<head><i>.fc0`.
4. **Train / inference** — один канон `cp_gameplay0` (или явный `--save-state`).

**Сделано в коде:** план имён из манифеста; нет `build_inference_states`; нет single-head fallback при `policy_heads`; нет `prefer_embedded_actions` / `summarize_inference_actions`.

**Антиавтоматизация:**

- Авто-discovery списка голов из нарезки или ROM.
- Второй permanently patched `inference_*.fc0` в `save_states/`.

### Критерий готовности (DoD)

- [x] Документированный ядерный Multi-head (≥2 головы) с переключением по `phase_id` (без игро-констант в `src/`)
- [x] Пилот RnA: с cold/title-like старта (`cp_title0`) эпизоды доходят до `phase_id=gameplay` при Multi-head; isolation ok
- [x] Gameplay-голова **не** активна на шагах title/intro (метрика `train/phase_head_isolation_ok`; smoke 0 bad / N steps)
- [x] Save states: схема §5–§6 (`cp_<head><i>`), один канон на точку train/inference; GUID только в embed/staging; сборка эталона пишет имена из YAML
- [x] Unit/smoke зелёные; Pluggable Core соблюдён *(минимальный train-smoke 2026-07-26)*
- [x] Антискоуп не нарушен; глоссарий и DESIGN обновлены под Multi-head

### Не делать (антискоуп)

- Несколько SB3 zip + `bundle.yaml` / PolicyRouter как продуктовый путь
- Скриптовый remap / «behavior on phase» вместо голов
- Возврат title/attract confirm-stop как замена разделению политик
- Игро-специфика title/cutscene RnA в `src/env/base_nes_env.py` / train-ядре
- Полный multi-genre / все боссы в этом TASK (задел API + пилот intro/gameplay)
- Ломать Discrete совместимость без явной пометки retrain / нового `genN`
- Плодить `inference_cp*` как второй канон того же кадра, что train gameplay-start (см. §5)
- Угадывать / авто-выводить список голов из save states или ROM (см. §6)

### Заметки / гипотезы

- **Смена курса (2026-07-25):** постановка v1 переведена с «отдельные zip + router» на **Multi-head / один genN.zip** (согласование с нарративом поколения и эфира).
- **Контекст (2026-07-23):** после GO-only exit и `start` отвергнут скриптовый non-gameplay; нужен multi-policy / multi-head.
- **Ось save states (пилот m1):** `cp_title0` → `cp_intro0` → `cp_gameplay0..4` → `cp_bossfight0` → `cp_intro1`; train/inference = `cp_gameplay0` @1243; GUID только в embed/staging.
- Будущие фазы (босс-детектор, пауза) — `phase_id` API уже есть; save states — `cp_<голова>0…`.
- Старые Discrete(9) без `start` несовместимы — пилот = новое поколение.
- **Минимальный train-пилот (2026-07-26):**
  - Команда: `train_ppo --smoke --smoke-session mh_pilot --timesteps 128 --n-envs 1 --n-steps 64 --batch-size 64 --dummy-vec --no-bc --no-resume --save-state save_states/cp_title0.fc0`
  - Multi-head: `title` / `intro` / `gameplay` / `bossfight`; старт с title save.
  - Isolation: `gameplay_on_title_intro=0/128`, `phase_head_isolation_ok=1`; итог `phase-head isolation: ok=True`.
  - Артефакты только в `tmp/smoke/mh_pilot/` (autodelete). Это проверка routing+метрики, не «intro научился жать start до gameplay».
- **Длинный learn-пилот (2026-07-26):**
  - Команда: `train_ppo --smoke --smoke-session mh_pilot_long --timesteps 16384 --n-envs 2 --n-steps 128 --batch-size 256 --n-epochs 2 --no-bc --no-resume --save-state save_states/cp_title0.fc0` (~12 мин, лог `tmp/bench/mh_pilot_long.log`).
  - Isolation: `ok=True`, `gameplay_on_title_intro=0/16384`.
  - Coverage: `reached_gameplay=True`, steps `title=239` / `intro=154` / `gameplay=15991` (старт title → проход intro → основная доля в gameplay).
  - `ep_rew_mean≈305`, `ep_len_mean≈1570` к концу прогона. Не оценка силы политики — приёмка routing + достижимость gameplay с Multi-head.
