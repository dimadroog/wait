# ISSUE_INFERENCE — FM2 playback показывает attract demo вместо геймплея агента

**Дата:** 2026-07-15  
**Этап BACKLOG:** 3.1–3.3 (inference FM2 / playlist / replay)  
**Ветка старта:** `issue/inference-fm2-replay`  
**Статус:** открыт — корневая причина локализована, фикс playback не реализован

**Связанные документы:** [ML_CONCEPT.md § FM2 из inference](ML_CONCEPT.md), [SCRIPTS.md § Inference / Replay](SCRIPTS.md), [BACKLOG.md § 3.1](BACKLOG.md)

---

## Симптом

При воспроизведении inference-клипов (`play_inference_fm2.py`, плейлист, ручное открытие FM2 в FCEUX) на экране **одинаковая картинка** — **встроенное attract mode demo** Rush'n Attack на заставке (до нажатия Start / старта миссии 1).

Ожидание: replay с **gameplay-start** (`states/inference_cp0.fc0`, кадр 18 эталона, room `0x00`) и нажатиями агента.

Факт: power-on → title screen → штатное демо игры. Записанные в FM2 кадры накладываются на неверное состояние эмулятора.

---

## Что работает (контраст)

| Компонент | Статус | Доказательство |
| --------- | ------ | -------------- |
| Запись inference (`run_inference.py`) | OK | bridge грузит `inference_cp0` через `-loadstate`; метрики `max_cp=4`, reward ≈497 согласуются с прохождением CP |
| Экспорт FM2 | OK | в заголовке есть `savestate 0x…`, уникальные GUID, разные digest кадров между эпизодами |
| Плейлист / dedupe | OK | `build_playlist`, `fm2_path` в attempts, remap GUID |
| Критерий BACKLOG 3.1 (self-contained FM2) | **частично** | embed в файле есть; **FCEUX 2.6.6 win64 не применяет его при `-playmovie`** (наблюдение 2026-07-15) |

---

## Корневая причина (подтверждена)

**FM2 playback не восстанавливает gameplay-start state.** FCEUX стартует с power-on; видно attract demo, а не сцену из `inference_cp0`.

Запись inference и просмотр FM2 — **разные контракты**:

| Режим | Старт состояния | Результат |
| ----- | --------------- | --------- |
| `run_inference` | `-loadstate inference_cp0.fc0` (bridge) | реальный геймплей, валидные метрики |
| `play_inference_fm2` | `-playmovie playback.fm2` + embedded `savestate` в заголовке | power-on → demo (savestate не подхватывается) |

Метрики эпизода (**не** «агент ничего не делал на заставке»): старт inference — кадр 18, CP0; CP4 требует прохождения комнат (`routes.yaml`). Reward ≈497 = 5× checkpoint_bonus − step_penalty.

---

## Отвергнутые / вторичные гипотезы

| Гипотеза | Вердикт | Комментарий |
| -------- | ------- | ----------- |
| **H1:** FCEUX путает FM2 по GUID в одной папке | частично верна | Реальна при нескольких FM2 с одним `romChecksum` в `fceux/portable/movies/`; **не объясняет** attract demo при пустом `movies/` |
| **H2:** одинаковый GUID в плейлисте | исправлена | `fm2_path` в attempts, remap в `build_playlist`; не влияет на картинку demo |
| **H3:** дедупликация схлопывает клипы | неверна | digest кадров различается (3/3 в прогоне 2026-07-15) |
| **H4:** бинарник `fceux64.exe` в `portable/` битый | неверна | MD5 идентичен чистому донору 2.6.6 win64 |
| **H5:** шаблон в `portable/movies/` — причина одинаковой картинки | **переоценена** | Перенос в `reference/header.fm2` — правильная гигиена (DESIGN § Pluggable Core), но **не лечит** playback без loadstate |
| **H6:** агент получает CP4 без действий на title screen | неверна | на title нет валидных CP; при записи старт — gameplay frame 18 |

---

## Полезные изменения в ветке (оставить)

| Изменение | Зачем |
| --------- | ----- |
| `reference/header.fm2` + `default_fm2_template()` из `games/…/reference/` | артефакты игры в плагине, не в `fceux/portable/` |
| `run_inference`: сохранение `fm2_path` в `attempts.jsonl` | корректный clone в `build_playlist` |
| `build_playlist`: `remap_fm2_guid` после fallback `export_fm2` | уникальные GUID клипов |
| `warn_portable_movies_pollution()` в preflight | ранний сигнал загрязнения `portable/movies/` |
| Тесты `test_fm2_export`, `test_playlist_embed` | регрессия export / playlist |
| Документация `ML_CONCEPT`, `SCRIPTS` | путь к шаблону |

---

## Что не решило playback (не продолжать в том же направлении)

- Очистка / сброс `fceux/portable/movies/` и `fceux.cfg` без loadstate при play
- Пересборка плейлиста из тех же `ep*.fm2` (копия без смены контракта play)
- Remap GUID в staging (нужен, но недостаточен)

---

## Пути решения (следующий спринт)

### R1 — Явный `-loadstate` перед `-playmovie` (рекомендуется)

В `play_inference_fm2.py`:

1. Извлечь embedded savestate из FM2 (или использовать `inference_cp0.fc0` как fallback).
2. Запуск: `-loadstate <state>` → `-playmovie playback.fm2` (проверить порядок аргументов FCEUX 2.6.6).
3. Staging: один `.fc0` рядом с ROM в `tmp/play_fm2/staging/`.

**Критерий:** визуально gameplay-start (room `0x00`, не title demo); ep3 короче ep1 по wall time.

### R2 — Проверить контракт embedded `savestate` в FM2

- Совпадение `guid` в заголовке и в blob savestate (`patch_savestate_movie_guid` — в `inference_cp0` может быть 0 GUID в blob).
- Минимальный repro: один FM2, Load ROM → Play Movie в чистом FCEUX без `portable/movies/*.fm2`.
- Обновить критерий BACKLOG 3.1, если embed не поддерживается win32-портом.

### R3 — Альтернатива: replay через bridge + Lua

Воспроизведение inputs из jsonl через `FceuxBridge` (как inference), без FM2 movie mode — тяжелее, но контракт совпадает с записью.

### R4 — Диагностика в CI / smoke

- `pytest` + `@pytest.mark.requires_fceux`: export FM2 → `play_inference_fm2` 1 клип → проверка RAM (room/y) через Lua или скриншот-хэш (опционально).

---

## Воспроизведение

```bash
# 1. Короткий inference + плейлист
./scripts/inference_local.sh --episodes 3 --max-steps 600 --stochastic \
  --save-episode-fm2 --build-playlist

# 2. Playback (симптом: attract demo)
./.venv/Scripts/python.exe scripts/play_inference_fm2.py \
  games/rushn_attack/missions/m1/logs/YYYYMMDD_playlist.json

# 3. Контраст: запись идёт с gameplay-start
# В логе run_inference: embedded savestate: states/inference_cp0.fc0
# human_playthrough frame 18: room 0x00, checkpoint 0
```

**Preflight:** `fceux/portable/movies/` должен быть **пуст** (нет FM2 с `romChecksum` игры).

---

## Чеклист закрытия

- [ ] `play_inference_fm2` стартует с `inference_cp0` (embed или `-loadstate`)
- [ ] Визуально: не attract demo; различимы ep1 vs ep3 по длительности/картинке
- [ ] Ручное открытие FM2 из `logs/` документировано (если остаётся ограничение FCEUX)
- [ ] BACKLOG 3.1 критерий уточнён под фактический контракт win32
- [ ] Smoke/integration тест с `requires_fceux` (опц.)

---

## Ссылки на код

| Файл | Роль |
| ---- | ---- |
| `scripts/play_inference_fm2.py` | playback staging, `-playmovie` |
| `src/fm2_export.py` | embed savestate, GUID, template |
| `src/inference_states.py` | `inference_cp0`, gameplay_start_frame |
| `scripts/build_inference_states.py` | сборка `inference_cp0.fc0` |
| `src/stream/run_inference.py` | запись с `-loadstate` |
| `games/…/reference/header.fm2` | шаблон метаданных ROM (не replay) |
