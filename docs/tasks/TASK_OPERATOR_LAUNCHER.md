# TASK_OPERATOR_LAUNCHER — операторский GUI-лаунчер

**Статус:** open (постановка — утвердить опции до кода)  
**Приоритет:** medium  
**Ветка:** `task/operator-launcher` — проработку этой задачи выполнять **только в этой ветке** (не в `main` и не в чужих task-ветках).  
**Зависит от:** [TASK_HYBRID_BROADCAST](archive/TASK_HYBRID_BROADCAST.md) (done); актуальный train CLI — [SCRIPTS.md § train_ppo](../SCRIPTS.md#train_ppopy) (сессии continue / snapshot / rollback, 2026-08).  
**Файлы:** новый `scripts/operator_launcher.py` (или `src/operator/launcher.py` + тонкий фасад); фасады CLI — `scripts/train_local.sh`, `scripts/inference_local.sh`, `scripts/build_playlist.py`, `scripts/play_inference_fm2.py`, `scripts/hybrid_episode_prep.py`, `scripts/build_broadcast_board.py`; `docs/SCRIPTS.md`  
**Контекст в чат:** этот файл + [SCRIPTS.md](../SCRIPTS.md) + [GLOSSARY.md](../GLOSSARY.md) (пул поколения, editorial, broadcast board)

Каркас: [TASK_BLANK.md](TASK_BLANK.md)

### Цель

Локальный операторский лаунчер на **tkinter / ttk** (без внешних UI-зависимостей): выбор рабочего контекста (игра / миссия / чекпоинт), запуск и остановка трёх сценариев — **Train**, **Inference live**, **Inference playlist**. CLI остаётся источником правды; лаунчер только собирает argv и вызывает существующие фасады (`subprocess`). Точный список полей на формах — **утвердить до реализации** (таблицы ниже — черновик).

### Объём v1 (вкладки)

| Вкладка | Намерение | Кнопки | CLI (ориентир) |
| ------- | --------- | ------ | -------------- |
| **Config** | Текущий контекст сессии лаунчера | применить | `--game`, `--mission`, save-state миссии |
| **Train** | Короткая сессия обучения / continue / откат | запустить, остановить | `train_local.sh` → `train_ppo` |
| **Inference live** | Live-инференс на эфире | запустить, остановить | `inference_local.sh` / `run_inference --live` |
| **Inference playlist** | Сбор пула + плейлист | собрать, запустить, остановить | `run_inference` → `build_playlist` → `play_inference_fm2` |

Опционально позже (не блокер v1): вкладки **Episode prep** / **Air** из hybrid-потока (`hybrid_episode_prep`, board mode) — см. [TASK_HYBRID_BROADCAST](archive/TASK_HYBRID_BROADCAST.md).

Smoke / bench — **вне** v1.

### Config — черновик полей (утвердить)

| Поле | Смысл | Примечание |
| ---- | ----- | ---------- |
| Игра | `game_id` | из `config/workspace.yaml` или список `games/*/` |
| Миссия | `mission_id` | под выбранной игрой |
| Чекпоинт миссии | save-state для env | `save_states/*.fc0` миссии; дефолт из манифеста |
| Модель (поколение) | `models/genN.zip` | общий выбор для Train / Inference |

Хранение: файл сессии лаунчера в `tmp/` или обновление `workspace.yaml` — **решить при реализации**.

### Train — черновик полей (утвердить)

Актуальный контракт train (после merge `feat/train-session-bc-rollback`):

| Поле на форме | CLI | Комментарий |
| ------------- | --- | ----------- |
| model-out | `--model-out models/genN.zip` | обязательно |
| timesteps | `--timesteps` | целевая суммарная цель на continue |
| n-envs | `--n-envs` | через `train_local.sh` дефолт **6** |
| BC refresh | `--bc-epochs N` | `0` = без BC; на **continue** BC не пропускается при `N > 0` |
| — | *(неявный continue)* | если `genN.zip` существует — добор; snapshot в `genN.prev.*` |
| пресет «новая сеть» | `--scratch` | пересоздать сеть на том же пути |
| пресет «откат» | `--rollback` | восстановить из `.prev`, без train |
| promote поколения | `--model-in` + новый `--model-out` | только если out **не** существует |

**Не на форме v1:** полный `train_task.json`, гиперпараметры PPO, `--allow-reduce-target`. Логирование — показ stdout/stderr в окне лаунчера + путь к лог-файлу (опция «писать в файл» — **утвердить**).

Удалённые флаги (не маппить): `--no-bc` → `--bc-epochs 0`; `--overwrite-model-out` → `--scratch`; bench-скрипты удалены.

### Inference live — черновик полей (утвердить)

| Поле | CLI | Комментарий |
| ---- | --- | ----------- |
| model / gen | `--model-version` или путь | из Config |
| live | `--live` | до Ctrl+C / кнопки «стоп» |
| game / mission | `--game`, `--mission` | из Config |

Остальные флаги `run_inference` — пресеты или «расширенные» (скрыты по умолчанию).

### Inference playlist — черновик полей (утвердить)

| Действие | CLI | Комментарий |
| -------- | --- | ----------- |
| Собрать пул | `inference_local.sh` / `run_inference` | накопление в `logs/genN/` |
| Собрать плейлист | `build_playlist` | editorial / обычный — **утвердить пресет** |
| Запустить | `play_inference_fm2` | один FCEUX на `playlist.json` |

Параметры пула (wipe / stochastic / playlist-cnt) — **утвердить** по карточкам [SCRIPTS.md](../SCRIPTS.md).

### Чеклист сессии

- [x] Hybrid-поток и пул `genN` — в `main` ([TASK_HYBRID_BROADCAST](archive/TASK_HYBRID_BROADCAST.md))
- [x] Train CLI: continue, snapshot `.prev`, `--rollback`, `--scratch`, BC на continue ([GLOSSARY § Снимок сессии](../GLOSSARY.md#снимок-сессии))
- [ ] **Утвердить** таблицы полей Config / Train / Inference live / Inference playlist (ревью оператора)
- [ ] Зафиксировать argv-маппинг (одна таблица «поле → флаг») в этом файле или в коде лаунчера
- [ ] Реализация `operator_launcher` на `task/operator-launcher`
- [ ] DoD: с лаунчера — train continue+BC, live, сбор и play плейлиста без ручного argv
- [ ] Регистрация entry point в [SCRIPTS.md](../SCRIPTS.md) по [алгоритму DESIGN](../DESIGN.md#регистрация-скриптов-в-scriptsmd)

### Критерий готовности (DoD)

- [ ] Config: смена game / mission / checkpoint / model сохраняется между запусками вкладок
- [ ] Train: запуск / остановка; пресеты continue, scratch, rollback; BC через `--bc-epochs`
- [ ] Inference live: запуск / остановка `--live`
- [ ] Inference playlist: собрать пул → плейлист → play; запуск / остановка
- [ ] Лаунчер не дублирует бизнес-логику (только argv → subprocess)
- [ ] Entry point в SCRIPTS.md

### Не делать (антискоуп)

- CustomTkinter / web UI / Electron
- OBS / Twitch / stream key
- Редактор `achievements.yaml` / номинаций
- Полный каталог SCRIPTS.md в v1
- Smoke / bench в GUI
- Подмена train/inference/playlist логики вне фасадов

### Заметки / гипотезы

- UI: **ttk**, Windows 10.
- Остановка процесса: terminate subprocess + `cleanup_bridge_sessions` (как при Ctrl+C в CLI).
- Train: короткие сессии + continue предпочтительнее одного длинного прогона; лаунчер может предлагать пресет «+500k steps + BC refresh 2 ep».
- Hybrid Episode/Air можно добавить второй итерацией без смены каркаса Config + Train + Inference.
