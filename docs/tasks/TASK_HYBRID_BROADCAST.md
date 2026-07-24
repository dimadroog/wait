# TASK_HYBRID_BROADCAST — editorial + live + board + slim Lua HUD

**Статус:** open  
**Приоритет:** high  
**Ветка:** `task/hybrid-broadcast` — проработку этой задачи выполнять только в этой ветке.  
**Зависит от:** [TASK_GEN_LOG_POOL](archive/TASK_GEN_LOG_POOL.md) (done — пул `logs/genN/` для editorial); концепт — [STREAMING_CONCEPT.md](../STREAMING_CONCEPT.md)  
**Файлы:** `src/achievements/playlist.py`, `src/achievements/evaluator.py`, `src/stream/run_inference.py`, `scripts/build_playlist.py`, `scripts/play_inference_fm2.py`, `scripts/inference_local.sh`, `config/achievements.yaml`, `fceux/lua/achievement_overlay_movie.lua`, `fceux/lua/achievement_overlay_playlist.lua`, `docs/SCRIPTS.md`, `docs/GAME_RUSHN_ATTACK.md` §5, опц. новый `streaming/` (board HTML/JSON)  
**Контекст в чат:** этот файл + [STREAMING_CONCEPT.md](../STREAMING_CONCEPT.md) §5–7 + [GLOSSARY.md](../GLOSSARY.md) (editorial, broadcast board, frontier, эпизод поколения)

### Цель

Реализовать content-production каркас hybrid-эфира: короткий [editorial](../GLOSSARY.md#editorial) (8–15 мин, без pad «до часа»), live-inference на [границе](../GLOSSARY.md#граница-прогресса-frontier), перебивки [broadcast board](../GLOSSARY.md#broadcast-board), тонкий Lua HUD. Тон: без обещаний прорывов и без агрессивного донат-CTA; скромная возможность «поддержать проект» на board допустима.

### Чеклист сессии

- [ ] Editorial builder: из пула `genN` собрать короткий `playlist.json` (лимит клипов / целевой airtime пакета ≪ 1 ч); **не** использовать `--target-airtime 1h`+pad как режиссёрский дефолт
- [ ] Контракт дельты: агрегаты eval `genN` vs `genN−1` для board (доля до CP_k, стена смертей) — минимальный JSON
- [ ] Broadcast board: OBS Browser Source (или статика) читает JSON; сцены Game / Board; стыки Editorial↔Live
- [ ] Lua HUD: ужать поля (gen, CP, короткий тег / смерть); не дублировать карту миссии и CTA
- [ ] Операторский поток: Board → editorial replay → Board → live (`run_inference --show-window` или согласованный live-entry) → Board
- [ ] Achievements YAML: сюжетные / честность / второстепенные по [GAME §5](../GAME_RUSHN_ATTACK.md#5-achievements-номинации-пилота); второстепенные не наполняют слот
- [ ] SCRIPTS.md + приёмка STREAMING §12; CLI-регистрация при смене флагов
- [ ] До gate ML: код/контракты можно готовить; установку OBS/Twitch не требовать для юнит-тестов board JSON / playlist length

### Критерий готовности (DoD)

- [ ] Из `genN` собирается editorial с airtime в диапазоне ориентира 8–15 мин (или явным коротким smoke-target), без обязательного pad до 1 ч
- [ ] Документирован и воспроизводим стык: replay editorial + запуск live + перебивка board (хотя бы локально без Twitch)
- [ ] Lua HUD не перекрывает геймплей критичными блоками текста; board показывает gen + границу/CP + режим
- [ ] Нет явного «донать на GPU / ETA» в board-текстах по умолчанию; максимум скромная строка поддержки
- [ ] STREAMING критерии §12 закрыты по смыслу (тестовый hybrid); GAME §5 отражает фактические slug после правки YAML

### Не делать (антискоуп)

- Chatting / podcasting / речь ведущего
- Миграция day→gen — [TASK_GEN_LOG_POOL](archive/TASK_GEN_LOG_POOL.md) (done)
- Полный продакшн Twitch-канал как обязательный DoD до gate ML (достаточно локального каркаса)
- Speedrun/WR-метрики как цель оверлея

### Заметки / гипотезы

- Board может жить в `streaming/board/` (HTML + `broadcast_board.json`); писать JSON из маленького скрипта/модуля после eval.
- Live на слабом CPU: короткие блоки попыток + Board-итог важнее непрерывного часа без ритма.
- `--target-airtime` можно оставить как утилиту измерения/smoke, но убрать из «собрать эфир» в SCRIPTS как главный сценарий.
