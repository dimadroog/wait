# TASK_OPERATOR_LAUNCHER — операторский GUI-лаунчер (Train / Inference / Play)

**Статус:** open (постановка формируется)  
**Приоритет:** medium  
**Ветка:** `task/operator-launcher` — проработку этой задачи выполнять **только в этой ветке** (не в `main` и не в чужих task-ветках).  
**Зависит от:** [TASK_PLAYLIST_AIRTIME](archive/TASK_PLAYLIST_AIRTIME.md) (done) — контракт `--target-airtime` / keep-preflight / pad уже в коде; уточнить поля форм Inference / Play по актуальному CLI.  
**Файлы:** уточнить после постановки; ориентиры — `docs/SCRIPTS.md`, `scripts/train_local.sh`, `src/train/train_ppo.py`, `scripts/inference_local.sh`, `src/stream/run_inference.py`, `scripts/play_inference_fm2.py`, `scripts/build_playlist.py`  
**Контекст в чат:** этот файл + [SCRIPTS.md](../SCRIPTS.md) + [TASK_PLAYLIST_AIRTIME](archive/TASK_PLAYLIST_AIRTIME.md) (карточки inference/playlist)

Каркас: [TASK_BLANK.md](TASK_BLANK.md)

### Цель

Локальный операторский лаунчер на **tkinter / ttk** (без внешних UI-зависимостей) для регулярного запуска трёх сценариев: **Train**, **Inference**, **Play**. CLI из [SCRIPTS.md](../SCRIPTS.md) остаётся источником правды; лаунчер — оболочка выбора опций и запуска. Объём v1 и точные опции **не фиксируем**, пока не закрыт airtime и не уточнены формы ниже.

### Объём v1 (намерение, не контракт)

| Сценарий | Намерение | Статус уточнения |
| -------- | --------- | ---------------- |
| **Train** | Запуск обучения с формой опций перед стартом | опции — **уточнить до реализации** |
| **Inference** | Сбор материала под эфир / плейлист (`--target-airtime`, keep/wipe preflight, pad) | контракт airtime готов — уточнить поля формы по [SCRIPTS](../SCRIPTS.md#inference) |
| **Play** | Запуск плейлиста или **цепочки плейлистов** за выбранный день / несколько дней | уточнить UX выбора дней; **открытый вопрос:** цепочка в **одном** экземпляре FCEUX vs последовательный перезапуск |

Smoke / bench / parse rollouts — **вне** этого черновика v1 (можно добавить позже отдельным пунктом постановки).

### Чеклист сессии (формирование → реализация)

- [x] Дождаться merge / usable состояния [TASK_PLAYLIST_AIRTIME](archive/TASK_PLAYLIST_AIRTIME.md)
- [ ] **Inference:** прочитать итоговый CLI и поток артефактов (`inference_local` / `run_inference` / `build_playlist` / preflight); зафиксировать поля формы и пресеты
- [ ] **Train:** согласовать минимальный набор опций и пресетов (что на форме, что остаётся только в CLI / `train_task.json`)
- [ ] **Play:** согласовать выбор дня/дней и поведение цепочки плейлистов; решить вопрос одного экземпляра FCEUX
- [ ] Дописать постановку: файлы, чеклист реализации, **DoD**, антискоуп
- [ ] Реализация лаунчера (после закрытия постановки)
- [ ] Регистрация entry point в [SCRIPTS.md](../SCRIPTS.md) по [алгоритму DESIGN](../DESIGN.md#регистрация-скриптов-в-scriptsmd)

### Критерий готовности (DoD)

_Заполнить после реализации playlist-airtime и уточнения Train / Inference / Play._

### Не делать (антискоуп, черновик)

- CustomTkinter / web UI / Electron
- OBS / Twitch / этап B стрима как часть этой задачи
- Подмена или дублирование бизнес-логики train/inference/playlist вне тонкой оболочки запуска
- Полный каталог всех скриптов из SCRIPTS.md в v1

### Заметки / открытые вопросы

- UI: **ttk** (stdlib), Windows 10 операторский хост.
- Inference нельзя детализировать по флагам до airtime: ожидаются `--target-airtime`, дневной retention UTC+3, keep-by-default preflight и pad-сбор плейлиста — см. задачу airtime.
- Play: сегодня типичный вход — `play_inference_fm2.py` + `logs/YYYYMMDD/playlist.json`; цепочка за несколько дней и один процесс FCEUX — предмет уточнения, не решение.
- Train: частые кандидаты в форму — timesteps / n-envs / checkpoint in·out / no-bc; финальный список — отдельным согласованием перед кодом.
