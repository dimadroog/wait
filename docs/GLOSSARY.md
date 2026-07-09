# GLOSSARY — термины проекта

> Единый словарь для [ML_CONCEPT.md](ML_CONCEPT.md) и [STREAMING_CONCEPT.md](STREAMING_CONCEPT.md).  
> Перекрёстные ссылки `#term` работают внутри этого файла (Preview).

---

### Achievement (inference)

Номинация попытки после [inference](#inference) (🏆 или 💀): правила в `config/achievements.yaml`, теги в `tags[]`, FM2-плейлист `{YYYYMMDD}_{idx}_{slug}_{seq}.fm2`. См. [ML_CONCEPT.md §8](ML_CONCEPT.md#8-форматы-данных).

### AI

**Artificial Intelligence** — в проекте: нейросеть ([PPO](#ppo)), которая играет в [NES](#nes) через [inference](#inference).

### BC

**Behavioral Cloning** — предобучение: модель копирует actions из записи [эталона](#etalon) (`demos/seg_*.npz`).

### Checkpoint (модель)

Файл весов [PPO](#ppo): `checkpoints/m1_vN.zip`. Не путать с [save state](#save-state) эмулятора.

### CP

**Checkpoint (игровой)** — узел прогресса CP0…CPn в `config/routes.yaml` миссии; первое достижение даёт награду в [RL](#rl).

### env

**Environment** — среда Gymnasium; общий каркас `BaseNesEnv` в `src/env/`, игровая фабрика `make_env()` в `games/<game_id>/env/`.

### FCEUX

Эмулятор NES: portable **2.6.6 win64** в `fceux/portable/fceux64.exe`; Lua проекта в `fceux/lua/`. Единый runtime для [эталона](#etalon), train и [inference](#inference). Окно для OBS Game Capture на эфире. Не Qt/SDL.

### FM2

Формат FCEUX Movie #2 — frame-perfect запись нажатий. В pipeline: [эталон](#etalon) (`reference/*.fm2`) и экспорт из [inference](#inference) (`scripts/export_fm2.py`).

### FPS

**Frames Per Second** — кадры в секунду; эфир: 30 FPS, эмулятор [NES](#nes): 60 FPS.

### Frame skip

Обработка каждого 4-го кадра NES → 15 decision/sec [BC](#bc) при 60 [FPS](#fps) эмулятора.

### Inference

Режим `model.predict()`: модель играет **без** обновления весов. Этап A — локально ([ML_CONCEPT.md](ML_CONCEPT.md)); этап B — на эфире ([STREAMING_CONCEPT.md](STREAMING_CONCEPT.md)).

### IPC

**Inter-Process Communication** — обмен Python ↔ Lua в [FCEUX](#fceux) (`fceux/lua/bridge.lua`).

### LLM

**Large Language Model** — в [MVP](#mvp) **не** используется для выбора сегментов; Phase 5+ (диспетчер задач).

### M1

**Mission 1** — первая миссия Rush'n Attack; scope [MVP](#mvp).

### Manifest

`config/playthrough_manifest.yaml` в каталоге миссии — каталог сегментов [эталона](#etalon), frames, save states.

### ML

**Machine Learning** — машинное обучение; раздел [ML_CONCEPT.md](ML_CONCEPT.md).

### MVP

**Minimum Viable Product** — первый рабочий контур: Rush'n Attack [M1](#m1), локальный CPU, один цикл train → [inference](#inference) → [дообучение](#doobuchenie).

### NES

**Nintendo Entertainment System** — 8-битная консоль; целевая платформа проекта.

### NG

**Ninja Gaiden** ([NES](#nes)) — в бэклоге; слишком сложен для старта pipeline.

### NVENC

**NVIDIA Encoder** — аппаратное кодирование видео на GTX 650 в OBS (см. [obs](#obs)).

### obs

Два значения в проекте:

1. **Observation** (ML) — наблюдение среды: стек из 4 кадров 84×84 в градациях серого, форма `(4, 84, 84)`, нормализованный вход CNN; кадры из [FCEUX](#fceux) через bridge (`obs_*.raw` / decode). Не путать с [RAM](#ram).
2. **Open Broadcaster Software** (стрим) — захват окна [FCEUX](#fceux), кодирование ([NVENC](#nvenc)), стрим на Twitch. На train не совмещать с [PPO](#ppo).



### Orphan (process)

**Orphan** — процесс без живого родителя (train/worker). В проекте: зависший `fceux64.exe` с `bridge.lua` после краша, Ctrl+C или обрыва [SB3](#sb3) `SubprocVecEnv`. Снимается `kill_orphan_fceux_bridge()` в `cleanup_bridge_sessions()` (`src/train/env_factory.py`).

### PPO

**Proximal Policy Optimization** — алгоритм RL; реализация в [SB3](#sb3).

### RAM

**Память NES** — адреса в картридже (`room`, `x`, `y`, `hp`…); читается через Lua в [FCEUX](#fceux). Не путать с ОЗУ ПК и не путать с [obs](#obs) (пиксели экрана).

### RL

**Reinforcement Learning** — обучение с подкреплением: агент получает числовую награду за действия в среде.

### ROM

**Read-Only Memory** — образ картриджа в `games/<game_id>/rom/`; в `.gitignore`, не показывать получение на эфире.

### Save state

Снимок состояния **эмулятора** [FCEUX](#fceux) (`states/cpN.fc`* в каталоге миссии); стартовая позиция эпизода при `env.reset()`.

### seg

**Сегмент** — фрагмент [эталона](#etalon) (`seg_001`…); demo `.npz`, границы в [manifest](#manifest).

### SB3

**Stable-Baselines3** — библиотека RL на PyTorch; в проекте: [PPO](#ppo), `SubprocVecEnv` / `DummyVecEnv`, callbacks (чекпоинты, progress %). Код: `src/train/train_ppo.py`, пакет `stable-baselines3` в `.venv/`.

### TAS

**Tool-Assisted Speedrun** — frame-perfect скрипт человека; **не** формат проекта (у нас [RL](#rl) + [inference](#inference)).

### WR

**World Record** — рекорд скоростного прохождения; **не** цель проекта.

### x_bucket

Дискретизация координаты `death_x` (ширина ≈32 px) для кластера смертей и триггера `death_cluster`.

### Дообучение

Продолжение обучения: `PPO.load(checkpoint)` + дополнительные timesteps, часто на проблемном сегменте с профилем `hot_zone`.

### Эталон

Полное прохождение миссии автором: [FM2](#fm2) + `reference/human_playthrough.jsonl` + save states в `games/<game>/missions/<m>/`; для [BC](#bc), [seg](#seg) и [дообучения](#doobuchenie).