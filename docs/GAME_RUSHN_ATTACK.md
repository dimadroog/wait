# GAME — Rush'n Attack

> Игро-специфичная концепция пилота. **Не runbook** заполнения конфигов — канон процедуры: [PROTOCOL_MISSION_REFERENCE.md](PROTOCOL_MISSION_REFERENCE.md).  
> Ядро платформы: [ML_CONCEPT.md](ML_CONCEPT.md) · Индекс: [README.md](README.md) · Эфир: [STREAMING_CONCEPT.md](STREAMING_CONCEPT.md) · [GLOSSARY.md](GLOSSARY.md)

**Роль в проекте:** первая игра для валидации pipeline (env → train → inference → дообучение). Не конечная цель платформы.

| Поле | Значение |
| ---- | -------- |
| `game_id` | `rushn_attack` |
| Title | Rush'n Attack (NES) |
| Пилот-миссия | `m1` |
| Корень данных | `games/rushn_attack/missions/m1/` |
| Env | `games/rushn_attack/env/` → `RushnAttackEnv` |
| ROM | `games/rushn_attack/rom/rushn_attack.nes` (не в git) |

---

## Содержание

1. [Env и действия](#1-env-и-действия)
2. [Награды и чекпоинты M1](#2-награды-и-чекпоинты-m1)
3. [Эталон и сегменты](#3-эталон-и-сегменты)
4. [Примеры конфигов](#4-примеры-конфигов)
5. [Приёмка пилота](#5-приёмка-пилота)
6. [Эфир / сезоны](#6-эфир--сезоны)
7. [Риски (игра)](#7-риски-игра)

---

## 1. Env и действия

Готового `gym-rushn-attack` нет. Среда — `games/rushn_attack/env/` поверх `BaseNesEnv` ([ML_CONCEPT.md §5](ML_CONCEPT.md#5-игра-и-среда)).

```yaml
# games/rushn_attack/game.yaml (черновик)
game_id: rushn_attack
title: "Rush'n Attack"
platform: nes
rom_file: rom/rushn_attack.nes
env_class: RushnAttackEnv
env_package: env
env_config: env_config.yaml
emulator:
  runtime: fceux/runtime.yaml
  lua_bridge: fceux/lua/bridge.lua
default_mission: m1
```

```python
from env.loader import make_env
env = make_env("rushn_attack", "m1")
```

### Пространство действий (M1)

```
noop | left | right | down | up | right+up | left+up | A | B | start
```

- **B** — атака ножом.
- **A** — использование оружия, когда доступно.
- **start** — кнопка Start (меню / title); в Discrete action space для Multi-head intro-головы.
- Диагонали — основа геймплея; прыжки: `up`, `right+up`, `left+up`.

Список в `games/rushn_attack/env_config.yaml`.

Там же: `screen_phases` → `info.phase_id` (`title` / `intro` / `gameplay`) и `policy_heads` (Multi-head).  
Фазы: title-поза; game over pose → `intro`; после `cp_gameplay*`/`cp_bossfight*` (sticky) или `room≥level_room_min` / `stage≥gameplay_min_stage` → `gameplay` (коридор m1 `room 0x00` не residual intro). Контракт Multi-head — `env_config.yaml` (`screen_phases` / `policy_heads`).

### Конец эпизода (`death_mode`)

| Режим | Поведение | Когда |
| ----- | --------- | ----- |
| `life_lost` | в **ядре** `BaseNesEnv`: `terminated` на первую потерю жизни; у **Rush'n Attack** death не режет эпизод | A/B / другие игры |
| `game_over` (**default**) | `died` на каждую потерю (−`death_penalty`); **выход эпизода RnA — только game-over-freeze** (не бюджет N смертей) | train / inference |

В RAM `lives` на смерти часто кратковременно **0** (анимация), затем respawn с lives−1 — поэтому счётчик смертей смотрит **события**, а не `lives==0`. На экране GAME OVER `lives` часто остаётся **6** — поэтому канон конца попытки не `lives`, а freeze.

Конец попытки у Rush'n Attack (`episode_end_title` → `RushnAttackEnv`) — **единственный критерий: game-over-freeze**:

- room + `title_x` + **`y ∉ title_ys`**, тот же `(x,y)` ≥ `game_over_freeze_confirm_steps` (default 32), `L≥1`, после начала попытки (`min_attempt_steps` / level-room / ≥1 death);
- title / attract standing **не** заканчивают эпизод;
- опционально `truncate_grace` / `truncate_cool` после `max_episode_steps`.  

`info.terminate_reason` при конце по freeze: `game_over_screen` (в ядре для других игр также возможен `death`; у RnA death не режет).

Smoke (random, `save_states/cp_gameplay0.fc0`, 2026-07-18, исторический): `life_lost` → `ep_len=2`; `game_over` → **≥300** steps без terminate после 1-й смерти.

---

## 2. Награды и чекпоинты M1

Общая модель CP / screen — [ML_CONCEPT.md §6](ML_CONCEPT.md#6-система-наград-и-чекпоинты). Ниже — числа и узлы пилота.

### Формула (`default`)

```python
reward = 0.0
if new_checkpoint > best_checkpoint:
    reward += 100 * (new_checkpoint - best_checkpoint)
    best_checkpoint = new_checkpoint
if died:
    reward -= 40
if mission_clear:
    reward += 1000
reward -= 0.005  # step penalty
```

| Компонент        | Значение     |
| ---------------- | ------------ |
| Checkpoint bonus | +100 за CP   |
| Death penalty    | −40          |
| Mission clear    | +1000        |
| Step penalty     | −0.005       |

### Профиль `hot_zone` (дообучение)

```yaml
reward_profile: hot_zone
hot_zone:
  x_from: 120
  x_to: 200
  dx_scale: 0.3
milestone_x: 200
milestone_bonus: 50
```

После дообучения — вернуть `default`.

### Чекпоинты миссии 1 (канон)

Канон в `config/routes.yaml` согласован с `head_save_states` (после аудита clear.fm2, 2026-07-26):

- Геймплей почти весь в `room 0x00`; прогресс — RAM **`stage`** (`0x0030`), не старые комнаты `0x0C`/`0x08`.
- Старт `cp_gameplay0` (`stage=0`) **без** платного CP — reset/стояние не дают бонус.
- Цепочка `requires_checkpoint` — нельзя перепрыгнуть узел.

```
CP1: after_second_ladder     (min_stage≥1)   ≈ после cp_gameplay1
CP2: ladders_done_mines_start (min_stage≥3)  = cp_gameplay2
CP3: after_red_enemy_ground  (min_stage≥6)   = cp_gameplay3
CP4: after_single_mine       (min_stage≥8)   = cp_gameplay4
CP5: mission1_boss           (min_stage≥9)   = cp_bossfight0
CP6: mission_clear           (flag)
```

Поле `stage` — в `config/ram_resolve.json` / `ram_map.md`.

---

## 3. Эталон и сегменты

**Shell** (относительно `games/rushn_attack/`): клипы оболочки игры — title / game over.

| Артефакт | Путь |
| -------- | ---- |
| FM2 game over → attract | `reference/game_over_to_attract*.fm2` |
| Scout shell-раунда | `reference/scout/<round>/` (после `ram_scout`; не в git) |

Якоря title / game over → [`env_config.yaml`](../games/rushn_attack/env_config.yaml) (`screen_phases`, `episode_end_title`).

**Миссия m1** (относительно `games/rushn_attack/missions/m1/`):

| Артефакт | Путь |
| -------- | ---- |
| FM2 эталона | `reference/clear.fm2` (+ research: `header.fm2`) |
| Jsonl эталона | `reference/human_playthrough.jsonl` |
| Manifest | `config/playthrough_manifest.yaml` (`head_save_states`, `train`/`inference`) |
| Routes | `config/routes.yaml` |
| Save states | `save_states/cp_<head><n>.fc0` из `head_save_states`; канон train/inference = `cp_gameplay0` |
| Demos (BC) | `reference/demos_for_bc/` (по необходимости) |
| Поколения модели | `models/genN.zip` |

Общий контракт записи / IPC — [ML_CONCEPT.md §7](ML_CONCEPT.md#7-эталонное-прохождение-и-дообучение).

### Выбор seg (пример пилота)

```
1. Триггер: death_cluster → room=0x06, x_bucket=160, checkpoint=2
2. Найти seg в manifest (checkpoint + room_ids)
3. Уточнить по x в human_playthrough.jsonl
4. save_state + hot_zone из гистограммы смертей
5. tasks/train_task.json → train_ppo.py
```

---

## 4. Примеры конфигов

### `config/playthrough_manifest.yaml` (фрагмент)

```yaml
playthrough_id: clear
game: rushn_attack
mission: "1"
fm2_file: reference/clear.fm2
head_save_states:
  gameplay:
    - id: cp_gameplay0
      frame: 1243
      label: level_start
train:
  save_state: save_states/cp_gameplay0.fc0
inference:
  save_state: save_states/cp_gameplay0.fc0
```

### `config/routes.yaml` (фрагмент)

```yaml
game: rushn_attack
mission: '1'
checkpoints:
  - id: 1
    name: after_second_ladder
    trigger: { room: '0x00', min_stage: 1 }
  - id: 2
    name: ladders_done_mines_start
    trigger: { room: '0x00', min_stage: 3, requires_checkpoint: 1 }
  - id: 5
    name: mission1_boss
    trigger: { room: '0x00', min_stage: 9, requires_checkpoint: 4 }
  - id: 6
    name: mission_clear
    trigger: { flag: mission_complete }
rewards:
  default:
    checkpoint_bonus: 100
    death_penalty: 40
    mission_clear_bonus: 1000
    step_penalty: 0.005
    kill_bonus: 0
```

### `tasks/train_task.json` (пример)

```json
{
  "task_id": "finetune_m1_seg003_v4",
  "trigger": {
    "type": "death_cluster",
    "room": "0x06",
    "x_bucket": 160,
    "deaths": 12
  },
  "model_in": "models/gen3.zip",
  "model_out": "models/gen4.zip",
  "segment_id": "seg_003",
  "save_state": "save_states/cp2.fc*",
  "route_config": "config/routes.yaml",
  "reward_profile": "hot_zone",
  "hot_zone": { "x_from": 128, "x_to": 192 },
  "ppo_timesteps": 500000,
  "reason": "12 смертей у x=150-170, room 0x06"
}
```

---

## 5. Приёмка пилота

Проверка pipeline платформы на этой игре ([ML_CONCEPT.md §12](ML_CONCEPT.md#12-критерии-приёмки-ml) ссылается сюда).

- [ ] Эталон M1: FM2 + jsonl; manifest + ≥3 seg
- [ ] `config/routes.yaml` с ≥4 CP, согласован с эталоном
- [ ] `ram_map.md` — ключевые адреса RAM
- [ ] `RushnAttackEnv` — smoke test
- [ ] `models/gen0.zip` обучена на CPU; inference на том же ПК
- [ ] Стабильно **CP2–3** (≥30% попыток)
- [ ] Цикл дообучения: триггер → `train_task.json` → train → новое поколение (`genN`)
- [ ] Rollback (`gen_new` хуже → `gen_prev`)

---

## 6. Эфир / сезоны

| Этап | Содержание |
| ---- | ---------- |
| Пилот / сезон 1 | M1; единица эфира — [эпизод поколения](GLOSSARY.md#эпизод-поколения) |
| Сезон 1b | M2–M6 (миссия = сезон; внутри — поколения / frontier report) |

Формат: live + OBS — [STREAMING_CONCEPT.md](STREAMING_CONCEPT.md). Захват: FCEUX → OBS 720p.

---

## 7. Риски (игра)

| Риск | Митигация |
| ---- | --------- |
| Нет готового gym | Custom env на `BaseNesEnv` |
| Неверные RAM-адреса | `ram_scout` / hex editor / jsonl эталона |
| Долгое обучение M1 | CP-награды; gate = CP2–3 |

Общие риски железа / PPO — [ML_CONCEPT.md §13](ML_CONCEPT.md#13-риски-ml).
