# TASK_OPERATOR_LAUNCHER — операторский GUI-лаунчер (Train / Pool / Episode / Air)

**Статус:** open (постановка уточнена под hybrid)  
**Приоритет:** medium  
**Ветка:** `task/operator-launcher` — проработку этой задачи выполнять **только в этой ветке** (не в `main` и не в чужих task-ветках).  
**Зависит от:** [TASK_HYBRID_BROADCAST](TASK_HYBRID_BROADCAST.md) (done — editorial / board / operator flow); [TASK_GEN_LOG_POOL](archive/TASK_GEN_LOG_POOL.md) (done — пул `logs/genN/`).  
**Файлы (ориентир):** новый entry `scripts/operator_launcher.py` (или `src/operator/launcher.py` + тонкий фасад); CLI: `scripts/train_local.sh`, `src/train/train_ppo.py`, `scripts/inference_local.sh`, `src/stream/run_inference.py`, `scripts/build_playlist.py`, `scripts/hybrid_episode_prep.py`, `scripts/build_broadcast_board.py`, `scripts/play_inference_fm2.py`; доки — `docs/SCRIPTS.md`  
**Контекст в чат:** этот файл + [SCRIPTS.md](../SCRIPTS.md) (inference / playlist / hybrid_episode_prep / board) + [STREAMING_CONCEPT.md](../STREAMING_CONCEPT.md) §5 (цикл эпизода) + [GLOSSARY.md](../GLOSSARY.md) (editorial, broadcast board, пул поколения)

Каркас: [TASK_BLANK.md](TASK_BLANK.md)

### Цель

Локальный операторский лаунчер на **tkinter / ttk** (без внешних UI-зависимостей) для регулярных сценариев вокруг **поколения модели** (`genN`), а не календарного дня. CLI из [SCRIPTS.md](../SCRIPTS.md) — источник правды; лаунчер — тонкая оболочка выбора опций и запуска.

v1 закрывает ритуал hybrid-эпизода: накопить [пул поколения](../GLOSSARY.md#пул-поколения) → короткий [editorial](../GLOSSARY.md#editorial) + [broadcast board](../GLOSSARY.md#broadcast-board) → replay / live. Обучение — отдельный режим той же оболочки.

### Объём v1 (режимы)

Не путать накопление пула с длиной эфира. Четыре режима:

| Режим | Смысл для оператора | CLI под капотом |
| ----- | ------------------- | --------------- |
| **Train** | Обучить / дообучить поколение | `train_local.sh` / `train_ppo` |
| **Pool** | Накопить попытки в `logs/genN/` | `inference_local.sh` / `run_inference` |
| **Episode prep** | Собрать короткий editorial + `broadcast_board.json` | `hybrid_episode_prep` (или `build_playlist --editorial` + `build_broadcast_board`) |
| **Air** | Editorial replay и/или live на эфире | `play_inference_fm2` + `run_inference --show-window`; смена `mode` board |

Рекомендуемая компоновка UI: вкладки Train / Pool / **Episode** (prep + чеклист Air) / либо отдельная Air. Smoke / bench / parse rollouts — **вне** v1.

### Поля форм (контракт постановки)

**Общее:** `--game` / `--mission` (дефолты пилота); выбор модели из `models/gen*.zip` → `model_version`.

**Train (минимум):** timesteps / n-envs / BC on·off / checkpoint in·out (или model out). Полный `train_task.json` не дублировать на форме.

**Pool:**
- model / wipe-gen-logs (keep по умолчанию) / episodes / stochastic;
- пресеты: «короткий прогон», «добор пула»;
- после накопления пула — Episode prep (не «набить час клипами»).

**Episode prep:**
- model; max airtime (8m / 12m / 15m); max clips; mode board на старте; support line on/off;
- после успеха показать airtime editorial и пути к `playlist.json` / board.

**Air:**
- выбор `logs/genN/playlist.json` (не дней);
- Editorial replay; Live (`--show-window`, короткий episodes);
- кнопки смены mode board: `open` → `live` → `close` (вызов `build_broadcast_board`);
- опционально: открыть `streaming/board/index.html` в браузере (без управления OBS).

Цепочка плейлистов за **календарные дни** — вне v1. Один FCEUX на один `playlist.json` — достаточно.

### Чеклист сессии

- [x] Дождаться usable [TASK_HYBRID_BROADCAST](TASK_HYBRID_BROADCAST.md) (editorial / board / пул `genN`)
- [x] Уточнить постановку под hybrid (режимы Pool / Episode / Air вместо «час pad» и Play по дням)
- [ ] Зафиксировать argv-маппинг полей форм ↔ CLI (таблица в заметках или отдельный раздел при реализации)
- [ ] Согласовать минимальный Train-набор (что на форме vs только CLI / `train_task.json`)
- [ ] Реализация ttk-лаунчера на ветке `task/operator-launcher` (после merge hybrid в `main`, если ещё не влито)
- [ ] DoD: с лаунчера пройти локальный hybrid-эпизод без длинного ручного argv
- [ ] Регистрация entry point в [SCRIPTS.md](../SCRIPTS.md) по [алгоритму DESIGN](../DESIGN.md#регистрация-скриптов-в-scriptsmd)

### Критерий готовности (DoD)

- [ ] С GUI можно: выбрать `genN` → при необходимости наполнить Pool → Episode prep → показать airtime editorial и пути артефактов
- [ ] С GUI можно: запустить editorial replay и короткий live (`--show-window`); сменить mode board и/или открыть HTML board локально
- [ ] Primary-пресеты ведут к editorial (`--editorial` / prep), а не к длинному плейлисту «на весь слот»
- [ ] Выбор материала — по `logs/genN/`, не по `YYYYMMDD`
- [ ] Лаунчер не содержит бизнес-логики train/inference/playlist (только argv → subprocess / существующие фасады)
- [ ] Entry point зарегистрирован в SCRIPTS.md

### Не делать (антискоуп)

- CustomTkinter / web UI / Electron
- Управление сценами OBS / Twitch / stream key (достаточно локального board HTML + JSON)
- Редактор `achievements.yaml` / номинаций
- Цепочки плейлистов за календарные дни; «несколько поколений подряд» — не обязательный DoD v1
- Полный каталог всех скриптов из SCRIPTS.md
- Подмена или дублирование бизнес-логики вне тонкой оболочки запуска
- Smoke / bench / parse rollouts в v1

### Заметки / гипотезы

- UI: **ttk** (stdlib), Windows 10 операторский хост.
- Источник правды по флагам — актуальные карточки [SCRIPTS](../SCRIPTS.md): `run_inference`, `build_playlist --editorial`, `hybrid_episode_prep`, `build_broadcast_board`, `play_inference_fm2`.
- Вкладка **Episode** может печатать тот же чеклист, что `hybrid_episode_prep` (Board → editorial → Board → live → Board), но кнопками.
- Реализацию начинать после того, как `task/hybrid-broadcast` доступен в базовой ветке лаунчера (merge в `main` или явное ответвление от hybrid).
