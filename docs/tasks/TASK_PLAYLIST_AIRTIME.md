# TASK_PLAYLIST_AIRTIME — retention day vs target airtime плейлиста

**Статус:** open  
**Приоритет:** high  
**Ветка:** `task/playlist-airtime` — проработку этой задачи выполнять **только в этой ветке** (не в `main` и не в чужих task-ветках).  
**Зависит от:** —  
**Файлы:** `config/achievements.yaml`, `src/jsonl_logs.py`, `src/achievements/evaluator.py`, `src/achievements/playlist.py`, `src/stream/run_inference.py`, `scripts/inference_local.sh`, `scripts/inference_preflight.py`, `scripts/build_playlist.py`, `docs/SCRIPTS.md`, `docs/STREAMING_CONCEPT.md`, `docs/GAME_RUSHN_ATTACK.md`, `docs/ML_CONCEPT.md`, `docs/GLOSSARY.md`  
**Контекст в чат:** этот файл + файлы из шпаргалки выше

### Цель

Развести **retention window** (пул attempts для tags / top_k / deja_vu) и **airtime** (длительность эфира = replay плейлиста). По умолчанию целевой эфир **1 час** realtime, не 4. Retention — **весь календарный день с полуночи UTC+3** (без `hours`). Сбор плейлиста — по `--target-airtime`, стоп когда Σ клипов ≥ N часов; наполнение **pad**.

### Решения (зафиксировано)

| Тема | Решение |
| ---- | ------- |
| Дефолт airtime | **1 час** realtime (~60 NES fps) |
| Retention | весь день; граница суток = **00:00 UTC+3** (не sliding hours) |
| Формула airtime | `Σ fm2_frames / 60` (+ hold между клипами); `fm2_frames ≈ episode_frames × frame_skip` |
| Сбор | `--target-airtime Nh`: inference + пересборка плейлиста, пока airtime ≥ N; стоп по эфиру, не по `--episodes` |
| Наполнение | **pad** (добивать клипами, чтобы закрыть N) |
| Preflight / логи дня | по умолчанию **сохранять** накопленное; учитывать уже имеющийся airtime перед добором; опционально wipe перед сбором |
| Бывшая «4 ч» | только старая двусмысленность — убрать из доков как «длину эфира»; не путать с retention |

### Чеклист сессии

- [ ] Доки: два термина *retention window* ≠ *airtime*; вычистить двусмысленность «4 ч» (ML / SCRIPTS / STREAMING / GAME §5 / GLOSSARY)
- [ ] Retention: день с полуночи **UTC+3**; одно место правды (`achievements.yaml` + `jsonl_logs` / evaluator); убрать зависимость от `RETENTION_HOURS` как sliding 4h
- [ ] Проверить, что `top_k` / `deja_vu` / `new_record` считают по дневному пулу и не ломаются
- [ ] Формула + хелпер оценки airtime плейлиста (`playlist.json` / FM2 frames, + hold)
- [ ] `--target-airtime` (дефолт 1h): цикл inference → build_playlist → пока Σ &lt; N; pad-политика
- [ ] Preflight: default keep day’s logs; учесть текущий airtime перед стартом; флаг опциональной очистки перед сбором
- [ ] SCRIPTS / STREAMING / GAME § achievements: CLI-примеры под N часов (и короткий smoke-target)
- [ ] Smoke: target 2–3 мин → playlist airtime ≥ target → `play_inference_fm2` не падает

### Критерий готовности (DoD)

- [ ] В доках нельзя прочитать retention/«4 ч» как длину эфира; дефолт airtime = 1h задокументирован
- [ ] Retention = календарный день UTC+3; одно место правды; `top_k` / `deja_vu` ок
- [ ] Оператор задаёт `--target-airtime` (или дефолт 1h) и получает плейлист с измеримым airtime ≥ N (или явный shortfall / прогресс)
- [ ] Preflight по умолчанию не сносит накопление дня; опциональный wipe есть
- [ ] Smoke 2–3 мин зелёный

### Не делать (антискоуп)

- OBS / Twitch / реальный эфир на канал
- Смена порядка блоков драматургии (кроме pad для длины)
- Train / FPS degradation
- Live inference на эфире (только playlist replay)
- Целевой эфир 4 часа как дефолт

### Заметки / гипотезы

- Путаница: `retention_hours: 4` воспринимали как «эфир 4 часа»; на деле это было окно отбора attempts.
- Граница дня **UTC+3** (= Europe/Moscow wall date), не UTC midnight из текущего `start_of_utc_day`.
- Pad: при коротких death-run клипах (~10–20 с) 1h ≈ сотни клипов; цикл должен уметь добирать, не только `--episodes 5`.
- Имеющийся `logs/<day>/` до старта вычитается из remaining target (keep-by-default).
