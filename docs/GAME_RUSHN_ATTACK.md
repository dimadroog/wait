# GAME — Rush'n Attack

> Игро-специфичная концепция пилота.  
> Ядро платформы: [ML_CONCEPT.md](ML_CONCEPT.md) · Индекс: [README.md](README.md) · Эфир: [STREAMING_CONCEPT.md](STREAMING_CONCEPT.md) · [GLOSSARY.md](GLOSSARY.md)

**Роль в проекте:** первая игра для валидации pipeline (env → train → inference → дообучение → плейлист). Не конечная цель платформы.

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
5. [Achievements (номинации пилота)](#5-achievements-номинации-пилота)
6. [Приёмка пилота](#6-приёмка-пилота)
7. [Эфир / сезоны](#7-эфир--сезоны)
8. [Риски (игра)](#8-риски-игра)

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
noop | left | right | down | up | right+up | left+up | A | B
```

- **B** — атака ножом.
- **A** — использование оружия, когда доступно.
- Диагонали — основа геймплея; прыжки: `up`, `right+up`, `left+up`.

Список в `games/rushn_attack/env_config.yaml`.

### Конец эпизода (`death_mode`)

| Режим | Поведение | Когда |
| ----- | --------- | ----- |
| `life_lost` | `terminated` на **первую** потерю жизни | A/B / старый reset-storm baseline |
| `game_over` (**default**) | `died` на каждую потерю жизни (−`death_penalty`); `terminated` после **N** смертей, N = lives на старте эпизода | train / inference env |

В RAM `lives` на смерти часто кратковременно **0** (анимация), затем respawn с lives−1 — поэтому `game_over` считает **события** потери жизни, а не `lives==0`. CLI: `--death-mode` у `train_ppo` / `smoke_env`.

Smoke (random, `states/cp0.fc0`, 2026-07-18): `life_lost` → `ep_len=2`; `game_over` → **≥300** steps без terminate после 1-й смерти.

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

### Черновик CP миссии 1

**4–6 узлов**, уточняются после эталона / RAM-разведки (`ram_map.md`).

```
CP0: старт миссии
CP1: первый значимый экран
CP2: лестница / вертикальный участок
CP3: backtrack или сложная зона (если есть)
CP4: pre-boss / финальный коридор
CP5: mission clear
```

Точные `room_id` и `(x,y)` — в `games/rushn_attack/missions/m1/ram_map.md`.

---

## 3. Эталон и сегменты

Пути относительно `games/rushn_attack/missions/m1/`.

| Артефакт | Путь |
| -------- | ---- |
| FM2 эталона | `reference/user_clear_v1.fm2` |
| Jsonl эталона | `reference/human_playthrough.jsonl` |
| Manifest | `config/playthrough_manifest.yaml` |
| Routes | `config/routes.yaml` |
| Save states | `states/cpN.fc*` |
| Demos | `demos/seg_*.npz` |
| Checkpoints модели | `checkpoints/m1_vN.zip` |
| Inference start | `states/inference_cp0.fc0` |

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
playthrough_id: user_clear_v1
game: rushn_attack
mission: 1
emulator: fceux
fceux_version: "2.6.6"
fm2_file: reference/user_clear_v1.fm2

segments:
  - id: seg_001
    name: start_to_first_ladder
    checkpoint_from: 0
    checkpoint_to: 1
    room_ids: [0x01, 0x02]
    demo_file: demos/seg_001.npz
    save_state: states/cp0.fc*

  - id: seg_002
    name: ladder_section
    checkpoint_from: 1
    checkpoint_to: 2
    room_ids: [0x03, 0x04]
    demo_file: demos/seg_002.npz
    save_state: states/cp1.fc*

  - id: seg_003
    name: mid_mission_alley
    checkpoint_from: 2
    checkpoint_to: 3
    room_ids: [0x05, 0x06]
    demo_file: demos/seg_003.npz
    save_state: states/cp2.fc*
```

### `config/routes.yaml` (фрагмент)

```yaml
game: rushn_attack
mission: 1

checkpoints:
  - id: 0
    name: start
    trigger: { room: 0x01 }
  - id: 1
    name: first_screen
    trigger: { room: 0x03 }
  - id: 2
    name: ladder
    trigger: { room: 0x05 }
  - id: 3
    name: mid_mission
    trigger: { room: 0x07 }
  - id: 4
    name: mission_clear
    trigger: { flag: mission_complete }

rewards:
  default:
    checkpoint_bonus: 100
    death_penalty: 40
    mission_clear_bonus: 1000
    step_penalty: 0.005

heuristics:
  mission_complete:
    min_progress_cp: 4
    room: 0x07
    x: 129
    min_y: 60
    max_y: 72
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
  "checkpoint_in": "checkpoints/m1_v3.zip",
  "checkpoint_out": "checkpoints/m1_v4.zip",
  "segment_id": "seg_003",
  "save_state": "states/cp2.fc*",
  "route_config": "config/routes.yaml",
  "reward_profile": "hot_zone",
  "hot_zone": { "x_from": 128, "x_to": 192 },
  "ppo_timesteps": 500000,
  "reason": "12 смертей у x=150-170, room 0x06"
}
```

---

## 5. Achievements (номинации пилота)

Идея и pipeline (evaluator, playlist, overlay) — [ML_CONCEPT.md §8](ML_CONCEPT.md#8-форматы-данных).  
Правила пилота сейчас в `config/achievements.yaml` (общий файл; содержание — про эту игру).

| Idx | slug | Overlay (RU) | Тип | Условие |
| --- | ---- | ------------ | --- | ------- |
| 01 | `mission_clear` | Клир миссии | 🏆 | `mission_clear == true` |
| 02 | `episode_reward` | Жадина | 🏆 | top‑K по `episode_reward` за 4 ч |
| 03 | `fastest_death` | Мгновенный респawn | 💀 | `died` и `episode_frames ≤ 3` |
| 04 | `many_achievements` | Тур CP | 🏆 | `len(achieved_checkpoints) ≥ 4` |
| 05 | `deep_run` | Почти финиш | 🏆 | `max_checkpoint ≥ 4` и не `mission_clear` |
| 06 | `deja_vu` | Déjà vu | 💀 | `(death_room, death_x_bucket)` ≥ 3 за 4 ч |
| 07 | `ladder_ouch` | Лестница съела | 💀 | `died` и `death_room == "0x08"` |
| 08 | `new_record` | Личный рекорд | 🏆 | новый max `max_checkpoint` для `model_version` |

`death_x_bucket = death_x // 16`.

**Сортировка внутри блока:** 02 — `episode_reward` ↓; 03 — `episode_frames` ↑; остальные — `timestamp` ↓.

**Порядок блоков на эфире:** `01 → 08 → 04 → 05 → 02 → 07 → 06 → 03`.

---

## 6. Приёмка пилота

Проверка pipeline платформы на этой игре ([ML_CONCEPT.md §12](ML_CONCEPT.md#12-критерии-приёмки-ml) ссылается сюда).

- [ ] Эталон M1: FM2 + jsonl; manifest + ≥3 seg
- [ ] `config/routes.yaml` с ≥4 CP, согласован с эталоном
- [ ] `ram_map.md` — ключевые адреса RAM
- [ ] `RushnAttackEnv` — smoke test
- [ ] `m1_v0.zip` обучена на CPU; inference на том же ПК
- [ ] Стабильно **CP2–3** (≥30% попыток)
- [ ] Цикл дообучения: триггер → `train_task.json` → train → новый checkpoint
- [ ] Rollback (v_new хуже → v_prev)

---

## 7. Эфир / сезоны

| Этап | Содержание |
| ---- | ---------- |
| Пилот / сезон 1 | M1 |
| Сезон 1b | M2–M6 (миссия за блок стримов) |

Захват: FCEUX → OBS 720p — [STREAMING_CONCEPT.md](STREAMING_CONCEPT.md).

---

## 8. Риски (игра)

| Риск | Митигация |
| ---- | --------- |
| Нет готового gym | Custom env на `BaseNesEnv` |
| Неверные RAM-адреса | `ram_scout` / hex editor / jsonl эталона |
| Долгое обучение M1 | CP-награды; gate = CP2–3 |

Общие риски железа / PPO — [ML_CONCEPT.md §13](ML_CONCEPT.md#13-риски-ml).
