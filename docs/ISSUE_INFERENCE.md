# ISSUE_INFERENCE — FM2 playback показывает attract demo вместо геймплея агента



**Дата:** 2026-07-15 (гипотезы M1–M8: 2026-07-16)  

**Этап BACKLOG:** 3.1–3.3 (inference FM2 / playlist / replay)  

**Ветка:** `issue/inference-fm2-replay`  

**Статус:** **открыт** — данные/embed OK; **movie readonly playback** на FCEUX (2.6.6 win64, 2.2.2 win32) не восстанавливает gameplay RAM/PPU. Исследование M/N закрыто 2026-07-16.



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

3. **Режимы FCEUX (уточнение 2026-07-16):** ось проблемы — не «FM2 vs save state» как артефакты, а **где state применяется**:
   - **emulation mode** — `-loadstate` без movie (`FceuxBridge`, `run_inference`): RAM + PPU согласованы;
   - **movie readonly** — `-playmovie … -readonly 1`: inputs из FM2, load embed/Lua load **не синхронизирует PPU** (P7–P16).
   Ось **где state сохранён** (свободный геймплей vs проигрывание movie) в проекте **не разведена** — все `.fc0` пайплайна сняты через `save_states.lua` при активном FM2 (см. M3–M4).



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



## Модель FCEUX: capture vs apply (2026-07-16)



Термины (для гипотез M*):



| Термин | FCEUX / проект | Пример |

| ------ | -------------- | ------ |

| **emulation mode** | ROM + опц. `-loadstate`, **без** `-playmovie`; ввод с joypad / bridge | `run_inference`, `FceuxBridge` |

| **movie readonly** | `-playmovie path.fm2 -readonly 1` | `play_inference_fm2.py` |

| **capture @ gameplay** | `savestate.save` при **неактивном** movie (свободная игра) | *не делали в репо* |

| **capture @ movie** | `savestate.save` при `movie.active()` | `save_states.lua` на кадре N эталона → `cp*.fc0`, `inference_cp0` |

| **cross-movie FCS** | blob с другого FM2 + патч GUID (`ensure_savestate_movie_guid`) | embed ep*.fm2 из `inference_cp0` (источник — `clear.fm2`) |

| **movie-bound FCS** | blob, снятый на frame 0 **того же** FM2, что replay | N1 / M6 — не опробовано |



**Запись FM2 «с любого кадра»:** внешний `.fc0` пайплайна не обязателен, если (а) FM2 с power-on (`clear.fm2`) или (б) FCEUX при ручной записи movie сам вшивает `savestate` в заголовок. Текущий inference-контракт — короткий клип + внешний `inference_cp0` + embed при экспорте (M1–M2).



### Гипотезы M1–M8 (режимы save state)



#### Запись FM2 без внешних states



| ID | Гипотеза | Вердикт | Проработка |

| -- | -------- | ------- | ---------- |

| M1 | Полный FM2 с power-on не требует внешнего `.fc0` для replay | **подтверждена** | `reference/clear.fm2`: inputs с кадра 1, Play Movie без `-loadstate` — эталон Phase 0 |

| M2 | Ручная запись movie с середины игры: FCEUX вшивает `savestate` в FM2 без отдельного файла | **правдоподобна (FCEUX)** | В репо не автоматизировано; альтернатива inference_cp0 + jsonl-export |



#### Ось «где сохранён» vs «где применён» (исследование пользователя)



| ID | Гипотеза | Вердикт | Проработка |

| -- | -------- | ------- | ---------- |

| M3 | FCS, снятый в **emulation mode**, **нельзя** применить для корректного **movie readonly** replay | **подтверждена (RAM); ось capture не уникальна** | § M-proto-1 шаги 3–5: gameplay-capture = inference_cp0 control на mf=8 |

| M4 | FCS, снятый при **movie playback**, **нельзя** применить в **emulation mode** | **опровергнута** | `inference_cp0` снят при проигрывании `clear.fm2`; `run_inference` (`-loadstate` без movie) — gameplay и метрики OK |

| M5 | Проблема playback — в **cross-movie FCS** (источник `clear.fm2`, цель ep-FM2), а не в capture @ movie как таковом | **частично подтверждена** | Патч GUID @5699 + refresh embed (P1–P4) не лечат PPU; тело FCS с кадра 18 эталона, но не frame 0 ep-FM2 |

| M6 | **Movie-bound FCS** (save на mf=0 того же ep-FM2) даёт корректный movie readonly replay | **отвергнута** | § M-proto-2: capture mf=1 уже `x=0`; bootstrap probe = original |

| M7 | Короткий FM2 (не с power-on) **обязан** иметь строку `savestate` в заголовке для `-playmovie` | **подтверждена** | P17: strip embed → `Error(s) reading state 0!` |

| M8 | Inference как полный FM2 (power-on + intro + агент) без `inference_cp0` | **отвергнута** | `clear.fm2` @ mf=18 и prefix 25f — `x=0`, не 129; `tmp/bench/remaining/` |



#### Сводка: реальная асимметрия FCEUX (win64)



```

                    apply →

              emulation          movie readonly

              (-loadstate)       (-playmovie)

capture ↓

@ movie       inference_cp0      embed / load / Lua

(clear.fm2)   → OK (запись)      → FAIL PPU (P7–P16)

@ gameplay    не тестировали      не тестировали (M3)

              M3: оба FAIL одинаково @ mf=8 (x=0, не 129)

@ same FM2    не тестировали      M6 **отвергнута** — bootstrap = original @ mf=8

mf=0          capture x=0 @ mf=1   нет улучшения

```



**Вывод по M3–M4:** формулировка «state с записи видео не работает в игре» **не совпадает** с данными проекта (M4). Формулировка «state не поднимает PPU в movie readonly» **совпадает** с P7–P16 и не зависит от того, gameplay это был или movie capture — для текущего `inference_cp0` capture был @ movie, apply @ emulation работает, apply @ movie — нет.



### Протокол проверки (оставшиеся M3, M6, N3)



#### § M-proto-1 — gameplay capture → movie readonly (M3)



| Шаг | Действие | Статус | Результат (2026-07-16) |
| --- | -------- | ------ | ---------------------- |
| 1 | ROM + `-loadstate inference_cp0`, **без** movie; проверка RAM | **OK** | emulation capture (одноразовый скрипт, удалён): `movie_active=false`, `room=0`, `x=129`, `lives=0` (эталон gameplay-start) |
| 2 | `savestate.save` при неактивном movie | **OK** | `tmp/bench/mproto1/gameplay_capture.fc0` (слот 0, emulation capture) |
| 3 | Тестовый FM2 с embed из шага 2 + 30–60 кадров | **OK** | `tmp/bench/mproto1/gameplay_capture.fm2`, `inference_cp0_control.fm2` (`build_empty_fm2`, 60 пустых кадров) |
| 4 | `-playmovie test.fm2 -readonly 1` + probe | **OK** | `movie_playback_probe.lua` @ mf=8: оба клипа `room=0`, `x=0`, `gameplay_like_ram=false` |
| 5 | Сравнение с контролем (`inference_cp0` embed) | **OK** | **Идентичный RAM** на mf=8; FCS различаются (68 байт), playback — нет |



**Вердикт M3 (2026-07-16):** gameplay-capture FCS **не** даёт корректный movie readonly replay. Но контроль (`inference_cp0`, capture @ movie) ведёт себя **так же** — ось «где сохранён» **не объясняет** расхождение; оба embed не восстанавливают gameplay RAM (`x=129`) при mf=8. Уточнённая формулировка: проблема в **apply @ movie readonly** (см. матрицу capture×apply), а не в gameplay vs movie capture.

Сводка probe (`tmp/bench/mproto1/mproto1_step3_5.json`):

```json
{
  "gameplay_capture": {"mf": 8, "room": 0, "x": 0, "gameplay_like_ram": false},
  "inference_cp0_control": {"mf": 8, "room": 0, "x": 0, "gameplay_like_ram": false}
}
```

PPU: автоматический probe не снимает картинку (P22); визуально ожидается title/attract как в P7 — RAM уже не совпадает с gameplay-start (`x=0` ≠ 129).



Детали шага 1: одноразовый Lua + Python harness (удалён после фиксации результатов в `tmp/bench/mproto1/`).

Артефакты: `tmp/bench/mproto1/mproto1_step3_5.json`, `tmp/bench/mproto1/gameplay_capture.fc0`.



#### § M-proto-2 — movie-bound FCS @ mf=0 (M6 / N1)



| Шаг | Действие | Статус | Результат (2026-07-16) |
| --- | -------- | ------ | ---------------------- |
| 1 | Исходный FM2 (`inference_cp0_control.fm2`) | **OK** | `tmp/bench/mproto1/inference_cp0_control.fm2` |
| 2 | `-playmovie` + capture @ mf≤1, movie active | **OK** | одноразовый harness (удалён); mf=1, `movie_active=true` |
| 3 | `savestate.save` → `playback_bootstrap.fc0` | **OK** | `tmp/bench/mproto2/playback_bootstrap.fc0` (185537 B, 2 GUID в blob) |
| 4 | Embed bootstrap в копию FM2 | **OK** | `inference_bootstrap.fm2` (одноразовая сборка) |
| 5 | Replay bootstrap без внешнего `-loadstate` | **OK** | probe @ mf=8 |
| 6 | Критерий gameplay-start | **FAIL** | см. ниже |



**Вердикт M6 / N1 (2026-07-16):** **отвергнута.** Movie-bound FCS не даёт `gameplay_like_ram` на mf=8.

| Probe | mf | room | x | gameplay_like_ram |
| ----- | -- | ---- | --- | ----------------- |
| capture @ save (mf=1) | 1 | 0 | 0 | false |
| playback original | 8 | 0 | 0 | false |
| playback bootstrap | 8 | 0 | 0 | false |

Bootstrap embed **отличается** от `inference_cp0` (185537 vs ~79 KB), но RAM-probe **идентичен** оригиналу. Уже на mf=1 при первом `-playmovie` RAM не gameplay-start (`x=0` ≠ 129) — сохранять «правильный» movie-bound state **не из чего**.

`ensure_savestate_movie_guid`: если target GUID уже в blob (movie-bound, 2 GUID) — не патчить.

Артефакты: `tmp/bench/mproto2/mproto2_results.json`, `tmp/bench/mproto2/playback_bootstrap.fc0`.



#### § M-proto-3 — fceux.cfg (N3)



| Шаг | Действие | Статус | Результат (2026-07-16) |
| --- | -------- | ------ | ---------------------- |
| 1 | Прочитать `fceux/portable/fceux.cfg` | **OK** | `bindSavestate 1`, `fullSaveStateLoads 0` (дефолт репо) |
| 2 | Probe playback @ mf=8 для 4 комбинаций | **OK** | см. таблицу |
| 3 | Restore cfg | **OK** | `bindSavestate 1`, `fullSaveStateLoads 0` |



**Ключи FCEUX 2.6.6 win64** (`fceux.cfg`, без кавычек):

| Ключ | UI | Назначение |
| ---- | -- | ---------- |
| `bindSavestate` | Bind savestates to movies | имя movie в `.fc0` |
| `fullSaveStateLoads` | Load full savestate-movies | не обрезать movie в **record** mode при loadstate |



**Probe** (`inference_cp0_control.fm2`, readonly `-playmovie`, mf=8):

| Вариант | bindSavestate | fullSaveStateLoads | room | x | gameplay_like_ram |
| ------- | ------------- | ------------------ | ---- | --- | ----------------- |
| baseline (репо) | 1 | 0 | 0 | 0 | false |
| bind1_full1 | 1 | 1 | 0 | 0 | false |
| bind0_full0 | 0 | 0 | 0 | 0 | false |
| bind0_full1 | 0 | 1 | 0 | 0 | false |



**Вердикт N3 (2026-07-16):** **отвергнута** для issue playback. Переключение `bindSavestate` / `fullSaveStateLoads` **не меняет** RAM-probe на mf=8. `fullSaveStateLoads` по документации FCEUX относится к **record** mode (truncate movie), не к readonly replay embed.

Артефакты: `tmp/bench/mproto3/mproto3_results.json` (патч `fceux.cfg` — вручную / одноразовый harness).



#### § N2-proto — официальный GitHub zip 2.6.6 (2026-07-16)



| Шаг | Результат |
| --- | --------- |
| Download | `tmp/bench/fceux-n2/fceux-2.6.6-win64.zip` |
| Extract | `fceux/portable_github_v266/` (side-by-side, не заменяет `portable/`) |
| MD5 `fceux64.exe` | `a8a75e0a20627d822d467c46dee9744b` — **совпадает** с `fceux/portable/` |
| Probe @ mf=8 (`FCEUX_HOME=portable_github_v266`) | `room=0`, `x=0`, `gameplay_like_ram=false` — **как win64 portable** |

**Вывод:** официальный релиз GitHub **не отличается** от установленного portable; гипотеза «битый exe» (H4) подкреплена.

### FCEUX 2.2.2 win32 (SourceForge, 2026-07-16)

| Шаг | Результат |
| --- | --------- |
| Download | `tmp/bench/fceux-n2/fceux-2.2.2-win32.zip` |
| Extract | `fceux/portable_222_win32/` (`fceux.exe`, не `fceux64.exe`) |
| `FCEUX_HOME` | `resolve_fceux_binary()` пробует `fceux64.exe`, затем `fceux.exe` |
| Probe @ mf=8 | `room=0`, `x=0`, `gameplay_like_ram=false` — **как 2.6.6 win64** |

**Вывод N2:** баг movie readonly + embed **не специфичен** для 2.6.6 win64 — воспроизводится на **2.2.2 win32**. Платформенный win64-баг **маловероятен**; скорее общая логика FCEUX movie/savestate load.

Ссылка: `https://sourceforge.net/projects/fceultra/files/Binaries/2.2.2/fceux-2.2.2-win32.zip/download`

### M8 — power-on FM2 без embed (2026-07-16)

| Клип | mf | room | x | gameplay_like_ram |
| ---- | -- | ---- | --- | ----------------- |
| `clear.fm2` | 8 | 0 | 0 | false |
| `clear.fm2` | 18 | 0 | 0 | false |
| `clear.fm2` prefix 25f | 18 | 0 | 0 | false |
| inference embed (контроль) | 18 | 0 | 0 | false |

**Вердикт M8:** обход через полный FM2 / power-on **не** восстанавливает gameplay RAM в movie readonly. Артефакт: `tmp/bench/remaining/remaining_results.json`.



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

- Патч GUID в cross-movie FCS без movie-bound bootstrap (M5) — см. P1–P4



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



| ID | Идея | Почему остаётся | Связь |

| -- | ---- | --------------- | ----- |

| N1 | **Playback-bootstrap `.fc0`**: movie-bound FCS @ mf≤1 | Capture уже `x=0`; bootstrap не лучше original | **= M6, отвергнута** |

| N2 | Другая версия / сборка FCEUX | **частично закрыта** | 2.6.6 GitHub = portable; **2.2.2 win32** — тот же probe FAIL; § N2-proto |

| N3 | `fceux.cfg`: `bindSavestate`, `fullSaveStateLoads` | **отвергнута** — 4 комбинации, probe идентичен | § M-proto-3 |

| — | Gameplay capture → movie replay (M3) | **закрыто 2026-07-16** | `tmp/bench/mproto1/mproto1_step3_5.json` |

| N4 | Smoke с `requires_fceux` + RAM probe @ gameplay | **добавлен** | `tests/test_fm2_playback_fceux.py` (fail до закрытия issue) |

| N5 | Перезапись `ep*.fm2` из pipeline (embed при export, не только staging) | **закрыта (данные)** | `export_episode_fm2_from_steps` пишет embed; `play_inference_fm2` refresh — staging; PPU не меняется |

| — | Полный FM2 inference с power-on (M8) | **отвергнута** | даже `clear.fm2` probe FAIL @ mf=18 |



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



---

## Итоги исследования (2026-07-16)

Все гипотезы M-proto / N2 / N3 / M8 / N4 / N5 проработаны. **Корневая проблема не в данных FM2 и не в выборе `.fc0`**, а в контракте FCEUX **movie readonly**: embed/Lua load не дают gameplay RAM (`x=129`) даже для эталона `clear.fm2` @ mf=18.

| Что проверено | Вердикт |
| ------------- | ------- |
| GUID / embed / refresh (P1–P4, N5) | данные OK; PPU нет |
| gameplay vs movie capture (M3) | оба FAIL одинаково |
| movie-bound bootstrap (M6, N1) | FAIL |
| fceux.cfg bind/full (N3) | без эффекта |
| FCEUX 2.6.6 GitHub / 2.2.2 win32 (N2) | тот же FAIL |
| power-on FM2 без embed (M8, `clear.fm2`) | RAM probe FAIL @ mf=18 |
| emulation `-loadstate` (`run_inference`) | **OK** (запись агента) |

### Фактический контракт FCEUX (win64, 2026-07-16)

| Операция | Режим | Результат |
| -------- | ----- | --------- |
| Запись агента | bridge `-loadstate inference_cp0` | gameplay, метрики OK |
| Эфир / replay | `-playmovie embed -readonly 1` | title/black; RAM `x=0` @ mf=8 |
| Эталон `clear.fm2` replay | power-on, без embed | RAM `x=0` @ mf=18 (probe); визуал эталона для Phase 0 работал при сборке states |

### Расхождение с BACKLOG 3.1

Критерий 3.1: «FM2 воспроизводится в FCEUX без `-loadstate`» — **формально** movie active, **фактически** не gameplay-start на экране. Критерий нужно уточнить: **PPU gameplay-start** или альтернативный путь эфира (не movie readonly).

### N4 — автоматический критерий

```bash
./.venv/Scripts/python.exe -m pytest tests/test_fm2_playback_fceux.py -m requires_fceux
```

Ожидание при закрытии issue: тесты **pass**. Сейчас: **fail** (`x≠129`) — известный баг.

### N5 — pipeline export

`run_inference` → `export_episode_fm2_from_steps` вшивает `savestate` при записи (`tests/test_fm2_export.py`). `play_inference_fm2.py` → `refresh_fm2_embedded_savestate` только в staging перед GUI; на PPU не влияет.

### Что остаётся открытым (вне scope исследования)

- Визуальный PPU-fix (другой эмулятор, форк FCEUX, не FM2 replay).
- P18 (strip embed + CLI loadstate без movie) — не приоритет; P16/P17 цепочка.
- Скриншот-хэш в N4 (опц.; RAM probe достаточен для регрессии).

---

## Чеклист закрытия



- [ ] Визуальный gameplay-start при playback (не title / black)

- [ ] HUD `REPLAY/GAMEPLAY` **и** совпадение PPU (x≈129, комната 1)

- [x] Контракт win64 документирован (§ «Фактический контракт FCEUX»)

- [x] Smoke `requires_fceux` с RAM assert (`tests/test_fm2_playback_fceux.py`; **fail** пока issue открыт)

- [x] BACKLOG 3.1 критерий уточнён под фактический контракт (§ «Расхождение с BACKLOG 3.1»)

- [x] M3 / § M-proto-1 — gameplay capture

- [x] M6 / § M-proto-2 — **отвергнута**

- [x] M8 — power-on FM2 — **отвергнута**

- [x] N3 / § M-proto-3 — **отвергнута**

- [x] N2 / § N2-proto — 2.6.6 + 2.2.2

- [x] N4 / N5 — smoke + pipeline export



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

| `fceux/lua/save_states.lua` | capture @ movie → `cp*.fc0` / `inference_cp0` |

| `fceux/lua/movie_playback_probe.lua` | RAM-probe при `-playmovie` (M-proto-1 шаги 4–5, N4) |

| `src/fm2_playback.probe_movie_playback` | Python-обёртка probe |

| `src/fm2_export.build_empty_fm2` | тестовые FM2 с embed (N4) |

| `src/fceux_bridge.py` | emulation mode: `-loadstate` без `-playmovie` |

| `tests/test_fm2_playback_fceux.py` | N4: RAM probe smoke (`requires_fceux`; fail до fix) |


