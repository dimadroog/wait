# GLOSSARY — термины проекта

> Единый словарь для [ML_CONCEPT.md](ML_CONCEPT.md), [STREAMING_CONCEPT.md](STREAMING_CONCEPT.md), [GAME_RUSHN_ATTACK.md](GAME_RUSHN_ATTACK.md).  
> Перекрёстные ссылки `#term` работают внутри этого файла (Preview).

---

### Achievement (inference)

Номинация попытки после [inference](#inference) (🏆 или 💀): правила в `config/achievements.yaml`, теги в `tags[]`, FM2-плейлист `{idx}_{slug}_{seq}.fm2`. Pipeline — [ML_CONCEPT.md §8](ML_CONCEPT.md#8-форматы-данных); номинации пилота — [GAME_RUSHN_ATTACK.md §5](GAME_RUSHN_ATTACK.md#5-achievements-номинации-пилота).

### AI

**Artificial Intelligence** — в проекте: нейросеть ([PPO](#ppo)), которая играет в [NES](#nes) через [inference](#inference).

### Checkpoint (модель)

Файл весов [PPO](#ppo): `checkpoints/m1_vN.zip`. Не путать с [save state](#save-state) эмулятора.

### CP

**Checkpoint (игровой)** — узел прогресса CP0…CPn в `config/routes.yaml` миссии; первое достижение даёт награду в [RL](#rl).

### env

**Environment** — среда Gymnasium; общий каркас `BaseNesEnv` в `src/env/`, игровая фабрика `make_env()` в `games/<game_id>/env/`.

### env-step

Один вызов `env.step(action)` — шаг среды: действие агента, новый [obs](#obs), награда, флаги `terminated`/`truncated`. Счётчик `total_timesteps` в [SB3](#sb3) — сумма env-steps по **всем** параллельным [env](#env) (`n_envs`). Не путать с кадром [NES](#nes): при [frame skip](#frame-skip) 4 один env-step ≈ 4 кадра эмулятора. В [MEASUREMENTS.md](MEASUREMENTS.md) throughput пишут как **env-steps/s** (часто «wall» или «steady»).

### FCEUX

Эмулятор NES: portable **2.6.6 win64** в `fceux/portable/fceux64.exe`; Lua проекта в `fceux/lua/`. Единый runtime для [эталона](#etalon), train и [inference](#inference). Окно для OBS Game Capture на эфире.

### FM2

Формат FCEUX Movie #2 — frame-perfect запись нажатий. В pipeline: [эталон](#etalon) (`reference/*.fm2`) и экспорт из [inference](#inference) (`scripts/export_fm2.py`).

### FPS

**Frames Per Second** — кадры в секунду; эфир: 30 FPS, эмулятор [NES](#nes): 60 FPS. В [train log](#train-log-rollout-table) поле `fps` — другое: [env-steps](#env-step)/[wall-clock](#wall-clock) при обучении, не кадры видео.

### Frame skip

Обработка каждого 4-го кадра NES → 15 decision/sec при 60 [FPS](#fps) эмулятора.

### Harness

**Harness** (обвязка эксперимента) — одноразовый или bench-only код для **изолированной** проверки гипотезы **вне** production-пайплайна: минимальный Lua + Python (или pytest `requires_fceux`), без playlist, overlay, staging продакшн-скриптов. Цель — чистота эксперимента (как N6, M-proto, B-proto, **F-proto**): сначала контракт [FCEUX](#fceux), потом внедрение.

| Аспект | Правило |
| ------ | ------- |
| Где | `tmp/bench/<session>/` через `artifact_quarantine_dir("bench", …)` |
| Артефакты | JSON результатов, скриншоты PPU; не `games/…/logs/`, не `checkpoints/` |
| Жизненный цикл | после фиксации вердикта в [ISSUE_INFERENCE.md](tasks/archive/ISSUE_INFERENCE.md) — harness-скрипт удалить, JSON оставить |
| Gate | [PPU](#ppu) на GUI оператором; headless probe — вспомогательный, не закрывает issue (P22) |
| Не путать с | `play_inference_fm2.py`, `run_inference.py`, `smoke_*.py` (регрессия/production) |

После закрытия [ISSUE_INFERENCE](tasks/archive/ISSUE_INFERENCE.md) / **[3.6](tasks/archive/TASK_FIRST_CAMPAIGN.md#36-inference-replay-fm2-gameplay-capture-f-proto)** одноразовые N6/F0 harnesses удалены. Регрессия embed: `movie_playback_probe.lua` + `probe_movie_playback` / `_ppu` в `tests/test_fm2_playback_fceux.py`.

### Inference

Режим `model.predict()`: модель играет **без** обновления весов (`run_inference.py`). Попытки → плейлист; эфир — replay плейлиста ([STREAMING_CONCEPT.md](STREAMING_CONCEPT.md)).

### IPC

**Inter-Process Communication** — обмен Python ↔ Lua в [FCEUX](#fceux) (`fceux/lua/bridge.lua`).

### M1

**Mission 1** — первая миссия пилота; см. [GAME_RUSHN_ATTACK.md](GAME_RUSHN_ATTACK.md).

### Manifest

`config/playthrough_manifest.yaml` в каталоге миссии — каталог сегментов [эталона](#etalon), frames, save states.

### ML

**Machine Learning** — машинное обучение; раздел [ML_CONCEPT.md](ML_CONCEPT.md).

### NES

**Nintendo Entertainment System** — 8-битная консоль; целевая платформа проекта.

### NG

**Ninja Gaiden** ([NES](#nes)) — в бэклоге; слишком сложен для старта pipeline.

### NVENC

**NVIDIA Encoder** — аппаратное кодирование видео на GTX 650 в OBS (см. [obs](#obs)).

### obs

Два значения в проекте:

1. **Observation** (ML) — наблюдение среды: стек из 4 кадров 84×84 в градациях серого, форма `(4, 84, 84)`, нормализованный вход CNN; кадры из [FCEUX](#fceux) через bridge (`obs_*.raw` / decode). Не путать с [RAM](#ram).
2. **Open Broadcaster Software** (стрим) — захват окна [FCEUX](#fceux) (playlist replay), кодирование ([NVENC](#nvenc)), стрим на Twitch.



### Orphan (process)

**Orphan** — процесс без живого родителя (train/worker). В проекте: зависший `fceux64.exe` (`bridge.lua` или сессия `tmp/bridge/`) и зависший `python` (`benchmark_train.py`, `train_ppo.py`, `stress_e2e_gate.py`, …) после краша, Ctrl+C или обрыва [SB3](#sb3) `SubprocVecEnv`. Снимается `kill_orphan_fceux_bridge()` в `cleanup_bridge_sessions()` (`src/train/env_factory.py`).

### PPO

**Proximal Policy Optimization** — алгоритм RL; реализация в [SB3](#sb3).

### PPU

**Picture Processing Unit** — чип отрисовки [NES](#nes); в проекте: **картинка на экране** [FCEUX](#fceux) (кадр 256×240), то, что видит оператор на эфире. Не путать с [RAM](#ram) (адреса `room`, `x`, `hp` через Lua) и с [obs](#obs) (стек 84×84 для CNN). Visual probe и критерий playback — по **PPU** (title vs gameplay); RAM-probe может не совпадать с экраном (RAM↔PPU desync, см. [ISSUE_INFERENCE.md](tasks/archive/ISSUE_INFERENCE.md)). Снимок в probe: `gui.gdscreenshot` в Lua.

### RAM

**Память NES** — адреса в картридже (`room`, `x`, `y`, `hp`…); читается через Lua в [FCEUX](#fceux). Не путать с ОЗУ ПК, с [PPU](#ppu) (экран) и с [obs](#obs) (пиксели для ML).

### RL

**Reinforcement Learning** — обучение с подкреплением: агент получает числовую награду за действия в среде.

### rollout

Один цикл обучения [PPO](#ppo) в [SB3](#sb3): (1) параллельный сбор `n_steps` шагов в каждом из `n_envs` [env](#env) → `n_envs × n_steps` [env-steps](#env-step); (2) обновление весов по собранному буферу (`n_epochs` проходов по batch). В [train log](#train-log-rollout-table) новая строка таблицы = завершённый rollout; `iterations` — их счётчик. Gate [5.0] = **2 rollout'а** при `n_steps=128`, `n_envs=8`, `timesteps=2048` (2×1024 env-steps).

### ROM

**Read-Only Memory** — образ картриджа в `games/<game_id>/rom/`; в `.gitignore`, не показывать получение на эфире.

### Save state

Снимок состояния **эмулятора** [FCEUX](#fceux) (`states/cpN.fc`* в каталоге миссии); стартовая позиция эпизода при `env.reset()`.

### seg

**Сегмент** — фрагмент [эталона](#etalon) (`seg_001`…); demo `.npz`, границы в [manifest](#manifest).

### SB3

**Stable-Baselines3** — библиотека RL на PyTorch; в проекте: [PPO](#ppo), `SubprocVecEnv` / `DummyVecEnv`, callbacks (чекпоинты, progress %). Код: `src/train/train_ppo.py`, пакет `stable-baselines3` в `.venv/`.

### Train log (rollout table)

Периодический вывод в консоль при `model.learn()` с `verbose=1` ([`train_ppo.py`](../src/train/train_ppo.py)). Печатается **после каждого [rollout'а](#rollout)** — одного цикла «сбор траекторий в [env](#env) → обновление весов [PPO](#ppo)». Дополнительные поля `progress_pct` и `target_timesteps` добавляет `TrainProgressPctCallback` (`src/train/progress_callback.py`); отключить: `--no-progress-pct`.

**Пример** (2-й rollout из трёх, `n_envs=6`, `n_steps=128`, цель `timesteps=2048`):

```
---------------------------------
| rollout/           |          |
|    ep_len_mean     | 2        |
|    ep_rew_mean     | -38.5    |
| time/              |          |
|    fps             | 5        |
|    iterations      | 2        |
|    time_elapsed    | 281      |
|    total_timesteps | 1536     |
|    progress_pct    | 75.0     |
|    target_timesteps| 2048     |
---------------------------------
```

| Поле | Секция | Значение |
| ---- | ------ | -------- |
| **rollout/** | метрики эпизодов за последний сбор данных | |
| `ep_len_mean` | rollout | средняя длина эпизода в [env-steps](#env-step). На пилоте [M1](#m1) типично **≈2** — короткие эпизоды, частые `reset()` ([reset storm](MEASUREMENTS.md)). |
| `ep_rew_mean` | rollout | средняя суммарная награда за эпизод за последний [rollout](#rollout) (профиль наград миссии). |
| **time/** | время и прогресс обучения | |
| `fps` | time | **не** [FPS](#fps) видео. Пропускная способность train: [env-steps](#env-step) / [wall-секунду](#wall-clock) **с начала сессии** (кумулятивный показатель [SB3](#sb3)). Сравнение с эталоном — [MEASUREMENTS.md](MEASUREMENTS.md). |
| `iterations` | time | число завершённых [rollout'ов](#rollout) (= число вызовов `learn` update). |
| `time_elapsed` | time | [wall-clock](#wall-clock) (с) с момента старта `learn()`. Разница между соседними строками ≈ длительность одного rollout'а. |
| `total_timesteps` | time | всего [env-steps](#env-step), собранных моделью (`num_timesteps`). За один [rollout](#rollout): `n_envs × n_steps` (напр. 6×128 = **768**). |
| `progress_pct` | time | доля цели в %: `100 × total_timesteps / target_timesteps` (проектный callback). |
| `target_timesteps` | time | целевое число [env-steps](#env-step) из CLI `--timesteps` или sidecar `.train.json` при `--resume`. |

Связанные команды: [`train_local.sh`](../scripts/train_local.sh), [train_ppo.py](SCRIPTS.md#train_ppopy). Деградация `fps` на длинном train — [TASK_TRAIN_FPS_DEGRADATION.md](tasks/TASK_TRAIN_FPS_DEGRADATION.md).

### TAS

**Tool-Assisted Speedrun** — frame-perfect скрипт человека; **не** формат проекта (у нас [RL](#rl) + [inference](#inference)).

### wall-clock

**Wall-clock** (wall time, «настенные часы») — реальное прошедшее время на машине, в отличие от симулированного времени игры или суммарного CPU по потокам. В проекте: `time_elapsed` в [train log](#train-log-rollout-table) (с); **wall env-steps/s** = `total_env_steps / wall_seconds` ([MEASUREMENTS.md](MEASUREMENTS.md)). **Steady** — тот же расчёт без первого [rollout'а](#rollout) (cold start FCEUX). Синоним в текстах: **wall-секунда**.

### WR

**World Record** — рекорд скоростного прохождения; **не** цель проекта.

### x_bucket

Дискретизация координаты `death_x` (ширина ≈32 px) для кластера смертей и триггера `death_cluster`.

### Дообучение

Продолжение обучения: `PPO.load(checkpoint)` + дополнительные timesteps, часто на проблемном сегменте с профилем `hot_zone`.

### Эталон

Полное прохождение миссии автором: [FM2](#fm2) + `reference/human_playthrough.jsonl` + save states в `games/<game>/missions/<m>/`; для [seg](#seg) и [дообучения](#doobuchenie).