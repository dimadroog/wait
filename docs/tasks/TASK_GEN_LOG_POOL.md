# TASK_GEN_LOG_POOL — пул логов по поколению вместо day-retention

**Статус:** open  
**Приоритет:** high  
**Ветка:** `task/gen-log-pool` — проработку этой задачи выполнять только в этой ветке.  
**Зависит от:** концепт hybrid — [STREAMING_CONCEPT.md](../STREAMING_CONCEPT.md) (ветка/merge `docs/streaming-hybrid`)  
**Файлы:** `src/jsonl_logs.py`, `src/attempt_logger.py`, `src/inference_input_logger.py`, `src/stream/run_inference.py`, `src/achievements/evaluator.py`, `src/achievements/playlist.py`, `src/inference_preflight.py`, `scripts/inference_local.sh`, `scripts/build_playlist.py`, `scripts/eval_achievements.py`, `scripts/export_fm2.py`, `config/achievements.yaml`, `tests/test_jsonl_logs_retention.py`, `tests/test_achievements_day_pool.py`, `docs/SCRIPTS.md`, `docs/ML_CONCEPT.md`, `docs/GLOSSARY.md`  
**Контекст в чат:** этот файл + [STREAMING_CONCEPT.md](../STREAMING_CONCEPT.md) + [GLOSSARY.md](../GLOSSARY.md#пул-поколения) + перечисленные `src/` / `scripts/`

### Цель

Убрать календарный [retention window](../GLOSSARY.md#retention-window-устарело) как политику пула attempts/achievements. Целевая ось — [пул поколения](../GLOSSARY.md#пул-поколения): `games/…/missions/<m>/logs/genN/` согласован с `models/genN.zip`. Сравнение прогресса и номинации — между поколениями, не между датами папок.

### Чеклист сессии

- [ ] Зафиксировать контракт путей: `logs/genN/{attempts,inference_inputs}.jsonl`, editorial артефакты рядом; `model_version` ↔ имя каталога
- [ ] Заменить `dated_day_dir` / `apply_retention` / `load_jsonl_window` на gen-scoped API в `jsonl_logs` (или тонкий слой над ним); удалить day-cutoff как отбор пула
- [ ] Перевести AttemptLogger, InferenceInputLogger, `run_inference`, preflight (wipe/keep), `build_playlist`, `eval_achievements`, `export_fm2` на gen-пути
- [ ] Achievements: `top_k` / `deja_vu` / `new_record` считают по пулу `genN`; убрать `retention_tz_offset_hours` из смыслового контракта (или оставить только если нужен timestamp display — не пул)
- [ ] Обновить/переименовать тесты day-pool → gen-pool; smoke без опоры на «сегодняшнюю дату»
- [ ] [SCRIPTS.md](../SCRIPTS.md) + as-is пометки в [ML_CONCEPT.md §8](../ML_CONCEPT.md#8-форматы-данных): пути и флаги соответствуют коду; регистрация CLI по [DESIGN](../DESIGN.md#регистрация-скриптов-в-scriptsmd) при смене публичных флагов
- [ ] Гигиена: не писать smoke в `models/`; карантин tmp по правилам проекта

### Критерий готовности (DoD)

- [ ] Новый inference с `--model genK.zip` пишет только в `logs/genK/`
- [ ] `eval_achievements` / `build_playlist` по умолчанию берут пул поколения модели, не `YYYYMMDD`
- [ ] Нет обязательной политики «календарный день UTC+3» для отбора тегов; глоссарий/SCRIPTS согласованы
- [ ] Тесты пула зелёные; дневные тесты удалены или переписаны
- [ ] Старые `logs/YYYYMMDD/` не требуются пайплайном (допускается игнор/ручная миграция без автомагии в DoD)

### Не делать (антискоуп)

- OBS / Twitch / Browser Source board (это [TASK_HYBRID_BROADCAST](TASK_HYBRID_BROADCAST.md))
- Полная перепись номинаций YAML под новые slug (можно оставить as-is правила на новом пуле; сюжетные slug — в hybrid-задаче)
- Обучение PPO / смена reward
- Обещания ETA железа / донат-CTA в UI

### Заметки / гипотезы

- Концепт уже описывает цель; код и SCRIPTS на момент открытия задачи ещё дневные — не подгонять доки под ложь, а менять код и сразу SCRIPTS.
- Имя каталога: `genN` vs `genN.zip` stem — выбрать один канон и держать в `model_version`.
- Preflight: вместо `--wipe-day-logs` → wipe/keep текущего gen (имя флага — часть CLI-регистрации).
