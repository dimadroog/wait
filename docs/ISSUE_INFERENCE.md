# ISSUE_INFERENCE — FM2 playback показывает attract demo вместо геймплея агента



**Дата:** 2026-07-15  

**Этап BACKLOG:** 3.1–3.3 (inference FM2 / playlist / replay)  

**Ветка:** `issue/inference-fm2-replay`  

**Статус:** **открыт** — GUID/embed в файле исправлены; **визуальный playback на FCEUX 2.6.6 win64 не починен** (сессия отладки 2026-07-15, вечер)



**Связанные документы:** [ML_CONCEPT.md § FM2 из inference](ML_CONCEPT.md), [SCRIPTS.md § Inference / Replay](SCRIPTS.md), [BACKLOG.md § 3.1](BACKLOG.md)



---



## Симптом



При воспроизведении inference-клипов (`play_inference_fm2.py`, плейлист, ручное открытие FM2 в FCEUX) на экране **не геймплей агента** — **title / attract demo** Rush'n Attack (меню «1 PLAYER») или чёрный экран. Overlay и метрики эпизода (CP4, reward ≈497) при этом **корректны** — клип записан с gameplay-start.



Ожидание: replay с **gameplay-start** (`states/inference_cp0.fc0`, кадр 18 эталона, room `0x00`, x=129) и нажатиями агента.



Факт: power-on / title → штатное демо или рассинхрон PPU↔RAM. Записанные в FM2 кадры накладываются на неверное **визуальное** состояние эмулятора.



---



## Что работает (контраст)



| Компонент | Статус | Доказательство |

| --------- | ------ | -------------- |

| Запись inference (`run_inference.py`) | OK | bridge: `-loadstate inference_cp0.fc0`; метрики `max_cp=4`, reward ≈497 |

| Экспорт FM2 | OK | `savestate 0x…` в заголовке, уникальные GUID, разные digest между эпизодами |

| Staging playback | OK | `refresh_fm2_embedded_savestate` из `inference_cp0`, `stage_playback_fc0`, mirror в `fcs/` |

| Плейлист / dedupe | OK | `fm2_path`, `remap_fm2_guid` |

| Lua overlay / HUD | OK | achievement overlay, диагностика `boot=…` |

| **Визуальный FM2 replay (win64 GUI)** | **FAIL** | title / black screen при активном movie и «успешном» Lua bootstrap |



---



## Корневая причина (уточнённая)



**Два слоя проблемы:**



1. **Данные (частично закрыто):** в старых `ep*.fm2` embedded FCS мог не иметь movie GUID @ offset 5699; `inference_cp0` патчится через `ensure_savestate_movie_guid`. Staging перезаписывает embed из `inference_cp0` + GUID клипа.



2. **FCEUX 2.6.6 win64 playback (открыто):** при `-playmovie` / `movie.play()` эмулятор **не восстанавливает PPU/gameplay-start** из embedded savestate и/или внешнего `.fc0`, даже когда Lua `savestate.load()` возвращает успех (`boot=OK`, `boot=PLAY+LD`, `boot=SYNC`). RAM (`room=0x00`) **не совпадает с картинкой** — на title к f≈8 уже `r=0x00`, `L=0` (см. `human_playthrough.jsonl`).



Запись и просмотр — **разные контракты**:



| Режим | Старт | Визуал | RAM / метрики |

| ----- | ----- | ------ | ------------- |

| `run_inference` | bridge `-loadstate inference_cp0.fc0` | gameplay | валидны |

| `play_inference_fm2` | movie mode (`-playmovie` / Lua `movie.play`) | title / black | частично «как gameplay», PPU нет |



---



## Отвергнутые гипотезы (ранние)



| ID | Гипотеза | Вердикт | Комментарий |

| -- | -------- | ------- | ----------- |

| H1 | FCEUX путает FM2 по GUID в `portable/movies/` | частично | Реальна при загрязнении `movies/`; **не объясняет** demo при пустой папке |

| H2 | Одинаковый GUID в плейлисте | исправлена | `remap_fm2_guid`; на картинку не влияет |

| H3 | Дедуп схлопывает клипы | неверна | digest кадров различается |

| H4 | Битый `fceux64.exe` | неверна | MD5 = донор 2.6.6 win64 |

| H5 | Шаблон в `portable/movies/` — причина demo | переоценена | Гигиена переноса в `reference/header.fm2` полезна, playback не лечит |

| H6 | Агент получает CP4 на title | неверна | CP на title невалидны; запись с frame 18 gameplay |



---



## Отвергнутые гипотезы (сессия playback 2026-07-15)



### Данные / embed / GUID



| ID | Гипотеза | Вердикт | Наблюдение |

| -- | -------- | ------- | ---------- |

| P1 | Нет GUID в FCS @5699 — **единственная** причина attract | **неверна как полное объяснение** | После `refresh_fm2_embedded_savestate` + `stage_playback_fc0` симптом **остаётся** |

| P2 | `remap_fm2_guid` в staging достаточен для картинки | неверна | Нужен, но недостаточен |

| P3 | Stale embed в `ep*.fm2` — playback читает старый attract-state | частично | `stage_playback_fc0` из `inference_cp0` исключает stale **для внешнего** `.fc0`; embed в FM2 refresh'ится; **визуал не меняется** |

| P4 | `playback.fc0` ≠ `inference_cp0` (битый mirror) | неверна | Отличие только GUID @5699; тело FCS совпадает |



### CLI: порядок `-loadstate` / `-playmovie`



| ID | Гипотеза | Вердикт | Наблюдение |

| -- | -------- | ------- | ---------- |

| P5 | Bridge-order: `-loadstate fc0` **перед** `-playmovie` | **неверна** (с overlay) | `NO-MOVIE`, «Movie playback stopped» |

| P6 | Doc-order: `-playmovie fm2 -readonly 1 -loadstate fc0 rom` | **неверна** | `Error(s) reading state 0!` (конфликт embed в FM2 + внешний loadstate) |

| P7 | Embed-only: `-playmovie fm2 -readonly 1 rom` (без `-loadstate`) | **неверна для PPU** | Movie active, overlay OK; **экран title**; HUD `REPLAY/GAMEPLAY r=0x00` к f≈8 |

| P8 | Явный `-loadstate` перед `-playmovie` + achievement overlay (ранний R1) | **неверна** | Attract demo сохраняется; порядок не даёт gameplay **на экране** |



### Lua bootstrap / savestate.load



| ID | Гипотеза | Вердикт | Наблюдение |

| -- | -------- | ------- | ---------- |

| P9 | `savestate.load(slot)` при `lives>10` (attract heuristic) | неверна | На title f≈8 уже `L=0` — bootstrap **не вызывается** |

| P10 | `savestate.load(slot)` при `mf<=1` после `-playmovie` | **неверна для PPU** | `boot=OK`; экран **title** |

| P11 | Mirror в `fceux/portable/fcs/{rom}.fc0` (+ `.playback.fc0`, `.playback.fm2.fc0`) | недостаточна | Слот доступен; load «успешен», картинка не меняется |

| P12 | `savestate.load` **после** `movie.play()` на `mf<=1` (`boot=PLAY+LD`) | **неверна для PPU** | f≈58: title, `r=0x00`, `boot=PLAY+LD` |

| P13 | `movie.playbeginning()` после load на `mf<=1` (`boot=SYNC`) | **неверна** | Пользователь: результат тот же (title) |

| P14 | Lua `movie.play()` вместо CLI `-playmovie` | **неверна** | `boot=PLAY`; title или black screen |

| P15 | Двухфазный Lua: ROM → `load` → `movie.play(embed)` | **неверна** | `boot=PLAY` (фаза `LD` краткая); title к f≈7 |

| P16 | Двухфазный: CLI `-loadstate` → Lua `movie.play` (strip embed) | **неверна** | Чёрный экран f≈15 `r=0x02` (траектория power-on); затем title с reload |



### Strip embed / конфликт state 0



| ID | Гипотеза | Вердикт | Наблюдение |

| -- | -------- | ------- | ---------- |

| P17 | Удалить `savestate` из FM2, полагаться на `-loadstate` | неверна | `Error(s) reading state 0!` при `-playmovie` без строки savestate |

| P18 | Strip embed + только CLI loadstate (без Lua play) | не тестировалось до конца | Отвергнуто цепочкой P16 / P5 |



### Диагностика RAM / HUD



| ID | Гипотеза | Вердикт | Наблюдение |

| -- | -------- | ------- | ---------- |

| P19 | `room==0x00` ⇒ gameplay (HUD `REPLAY/GAMEPLAY`) | **неверна** | Title к f≈8 уже `r=0x00` (`human_playthrough` frame 8: `0x05`, но в probe/power-on+movie — `0x00`) |

| P20 | `lives>10` ⇒ title phase | частично | Ранние кадры attract; на title после demo `L=0` — эвристика бесполезна |

| P21 | `mf < gameplay_start_frame (18)` ⇒ title в HUD | частично верна как **метка movie**, не как PPU | Inference FM2: frame 1 = первый кадр **агента**, не кадр 18 эталона; HUD не отражает экран |

| P22 | Headless probe Lua (`-noicon`, no GUI) воспроизводит GUI | неверна | `registerafter` / IO в headless ненадёжны; GUI — единственный валидный тест |



### Прочее (ранее отвергнуто, зафиксировать)



| ID | Гипотеза | Вердикт |

| -- | -------- | ------- |

| P23 | `movie.playbeginning()` при init скрипта | неверна — «No movie loaded» / stop |

| P24 | Replay через `FceuxBridge` + jsonl вместо FM2 | **идеологически отклонён** — см. ниже |



---



## Что не решило playback (не продолжать без новой идеи)



- Очистка `fceux/portable/movies/`, `fceux.cfg`

- Пересборка плейлиста / remap GUID / refresh embed **без смены контракта FCEUX**

- Любая комбинация **embed + внешний `-loadstate`** в одном CLI-вызове

- Lua `savestate.load` до/после `movie.play` / `playbeginning` на win64 GUI

- Strip embed при сохранении `-playmovie` в CLI

- Bridge-order `-loadstate` перед `-playmovie` (с `achievement_overlay.lua`)

- Эвристики HUD по `room` / `lives` как критерий закрытия issue

- **Replay через bridge + jsonl** — обход FM2; эфир/OBS завязаны на movie mode (BACKLOG 3.1–3.2)



---



## Полезные изменения в ветке (оставить)



| Изменение | Зачем |

| --------- | ----- |

| `reference/header.fm2`, `default_fm2_template()` | артефакты в плагине |

| `ensure_savestate_movie_guid`, `refresh_fm2_embedded_savestate` | корректный embed + GUID |

| `src/fm2_playback.py` (`stage_playback_fc0`, `stage_external_playback`) | staging helpers, тесты, будущий bootstrap |

| `achievement_overlay.lua` HUD (`REPLAY/TITLE`) | диагностика playback |

| `run_inference`: `fm2_path` в attempts | playlist |

| Тесты `test_fm2_export`, `test_fm2_playback`, `test_playlist_embed` | регрессия данных |

| `warn_portable_movies_pollution()` | preflight |



---



## Направления, **не** опробованные до конца (не отвергнуты, но нет результата)



| ID | Идея | Почему остаётся |

| -- | ---- | --------------- |

| N1 | **Playback-bootstrap `.fc0`**: save state в FCEUX **при активном movie frame 0** того же FM2 (movie-bound FCS) | `inference_cp0` сохранён с `clear.fm2`, не с ep-FM2; load при readonly может требовать sync blob |

| N2 | Другая версия / сборка FCEUX (не 2.6.6 win64) | Баг может быть платформенным |

| N3 | `fceux.cfg`: «Load full savestate-movies», «Bind savestates to movies» | Не проверялось систематически |

| N4 | Smoke с `requires_fceux` + скриншот-хэш / RAM x,y @ gameplay | Нет автоматического критерия «зелёного» playback |

| N5 | Перезапись `ep*.fm2` из pipeline после фикса GUID (не только staging) | Улучшает self-contained, не доказано для PPU |



---



## Текущий контракт кода (не закрывает issue)



```

staging: remap_fm2_guid → refresh embed from inference_cp0
CLI:     fceux -lua achievement_overlay.lua -playmovie playback.fm2 -readonly 1 rushn_attack
Lua:     диагностический HUD; без savestate bootstrap

```



**Фактический результат (2026-07-15):** title screen; см. таблицы P1–P24.



---



## Воспроизведение



```bash

./.venv/Scripts/python.exe scripts/play_inference_fm2.py \

  games/rushn_attack/missions/m1/logs/20260715_ep0001.fm2 --skip-preflight

```



Контраст записи:



```bash

# run_inference: embedded savestate: states/inference_cp0.fc0

# human_playthrough frame 18: room 0x00, x=129 (gameplay-start)

```



**Preflight:** `fceux/portable/movies/` пуст.



---



## Чеклист закрытия



- [ ] Визуальный gameplay-start при playback (не title / black)

- [ ] HUD `REPLAY/GAMEPLAY` **и** совпадение PPU (x≈129, комната 1)

- [ ] Контракт win64 документирован (или смена эмулятора/версии)

- [ ] Опц.: smoke `requires_fceux` со скриншот/RAM assert

- [ ] BACKLOG 3.1 критерий уточнён под фактический контракт



---



## Ссылки на код



| Файл | Роль |

| ---- | ---- |

| `scripts/play_inference_fm2.py` | staging, запуск FCEUX |

| `src/fm2_playback.py` | argv, staging helpers |

| `src/fm2_export.py` | embed, GUID, `refresh_fm2_embedded_savestate` |

| `fceux/lua/achievement_overlay.lua` | overlay + HUD + sync bootstrap |

| `games/…/states/inference_cp0.fc0` | gameplay-start state |

| `games/…/reference/human_playthrough.jsonl` | эталон room/x по кадрам |

| `src/stream/run_inference.py` | запись с bridge `-loadstate` |


