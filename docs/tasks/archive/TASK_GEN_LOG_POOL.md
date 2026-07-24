# TASK_GEN_LOG_POOL — пул логов по поколению вместо day-retention

**Статус:** done  
**Закрыто:** 2026-07-24 — `logs/genN/` + `--wipe-gen-logs`; day-retention убран из кода/CLI; merge `b8a6bf0` в `main`.  
**Приоритет:** high  
**Ветка:** `task/gen-log-pool`  
**Зависит от:** концепт hybrid — [STREAMING_CONCEPT.md](../../STREAMING_CONCEPT.md) (ветка/merge `docs/streaming-hybrid`)  
**Файлы:** `src/jsonl_logs.py`, `src/attempt_logger.py`, `src/inference_input_logger.py`, `src/stream/run_inference.py`, `src/achievements/evaluator.py`, `src/achievements/playlist.py`, `src/inference_preflight.py`, `scripts/inference_local.sh`, `scripts/build_playlist.py`, `scripts/eval_achievements.py`, `scripts/export_fm2.py`, `config/achievements.yaml`, `tests/test_jsonl_logs_gen_pool.py`, `tests/test_achievements_gen_pool.py`, `docs/SCRIPTS.md`, `docs/ML_CONCEPT.md`, `docs/GLOSSARY.md`  
**Контекст в чат:** этот файл + [STREAMING_CONCEPT.md](../../STREAMING_CONCEPT.md) + [GLOSSARY.md](../../GLOSSARY.md#пул-поколения) + перечисленные `src/` / `scripts/`

### Цель

Убрать календарный [retention window](../../GLOSSARY.md#retention-window-устарело) как политику пула attempts/achievements. Ось — [пул поколения](../../GLOSSARY.md#пул-поколения): `games/…/missions/<m>/logs/genN/` согласован с `models/genN.zip`. Сравнение прогресса и номинации — между поколениями, не между датами папок.

### Чеклист сессии

- [x] Зафиксировать контракт путей: `logs/genN/{attempts,inference_inputs}.jsonl`, editorial артефакты рядом; `model_version` ↔ имя каталога
- [x] Заменить `dated_day_dir` / `apply_retention` / `load_jsonl_window` на gen-scoped API в `jsonl_logs`; удалить day-cutoff
- [x] Перевести AttemptLogger, InferenceInputLogger, `run_inference`, preflight (wipe/keep), `build_playlist`, `eval_achievements`, `export_fm2` на gen-пути
- [x] Achievements: `top_k` / `deja_vu` / `new_record` по пулу `genN`; убран `retention_tz_offset_hours`
- [x] Тесты day-pool → gen-pool; smoke без «сегодняшней даты»
- [x] [SCRIPTS.md](../../SCRIPTS.md) + [ML_CONCEPT.md §8](../../ML_CONCEPT.md#8-форматы-данных); CLI-регистрация
- [x] Гигиена: без smoke в `models/`; без day-shim / compat-кода

### Критерий готовности (DoD)

- [x] Новый inference с `--model genK.zip` пишет только в `logs/genK/`
- [x] `eval_achievements` / `build_playlist` по умолчанию берут пул поколения модели, не `YYYYMMDD`
- [x] Нет обязательной политики «календарный день UTC+3» для отбора тегов; глоссарий/SCRIPTS согласованы
- [x] Тесты пула зелёные; дневные тесты удалены/переписаны
- [x] Старые `logs/YYYYMMDD/` не требуются пайплайном (игнор; без автомиграции)

### Не делать (антискоуп)

- OBS / Twitch / Browser Source board (это [TASK_HYBRID_BROADCAST](TASK_HYBRID_BROADCAST.md))
- Полная перепись номинаций YAML под новые slug
- Обучение PPO / смена reward
- Обещания ETA железа / донат-CTA в UI
- Автомиграция day→gen; compat-shim «на всякий случай»

### Заметки / гипотезы

- Канон каталога: stem модели (`gen1` из `gen1.zip`), не имя с `.zip`.
- Preflight: `--wipe-gen-logs` (вместо `--wipe-day-logs`).
- Аудит артефактов (m1): на диске остались только `logs/YYYYMMDD/` (20260718–20260724); gen-пула до миграции не было — оператор может оставить day-папки вручную или удалить; пайплайн их не читает.
