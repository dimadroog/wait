# ISSUE_INFERENCE — FM2 playback показывает attract demo вместо геймплея агента



**Дата:** 2026-07-15 (M/N: 2026-07-16; N6 + visual: 2026-07-16; B-proto: 2026-07-16; F-proto: 2026-07-16; **G0 + C1–C3: 2026-07-16**)

**Этап BACKLOG:** 3.4 (jsonl артефакты) · **3.5 закрыт (B0 FAIL)** · **[3.6](BACKLOG.md#36-inference-replay-fm2-gameplay-capture-f-proto) закрыт** (FM2-native, оператор C1–C3 PASS)

**Ветка:** `issue/inference-fm2-replay` (готово к merge в master)

**Статус:** **закрыт** — корневая причина: `inference_cp0` / `gameplay_start_frame=18` указывали на **title** (ложный критерий `room=0,x=129` при `lives=0`). Реальный gameplay = кадр **1250**. После rebuild FCS + фазы C: export / `play_inference_fm2` / playlist → **PPU gameplay** (оператор PASS 2026-07-16).



**Связанные документы:** [ML_CONCEPT.md § FM2 из inference](ML_CONCEPT.md), [SCRIPTS.md § Inference / Replay](SCRIPTS.md), [BACKLOG.md § 3.6](BACKLOG.md#36-inference-replay-fm2-gameplay-capture-f-proto)



---



## Симптом



При воспроизведении inference-клипов (`play_inference_fm2.py`, плейлист, ручное открытие FM2 в FCEUX) на экране **не геймплей агента** — **title / attract demo** Rush'n Attack (меню «1 PLAYER») или чёрный экран. Overlay и метрики эпизода (CP4, reward ≈497) **корректны в emulation** (`run_inference`, bridge `-loadstate`). **N6 + visual:** тот же PPU-симптом на native `movie.record`, pipeline export и staged replay — не сводится к «пайплайн пишет FM2 неправильно».



Ожидание: replay с **gameplay-start** (`states/inference_cp0.fc0`, кадр 18 эталона, room `0x00`, x=129) и нажатиями агента.



Факт: power-on / title → штатное демо или рассинхрон PPU↔RAM. Записанные в FM2 кадры накладываются на неверное **визуальное** состояние эмулятора.



---



## Что работает (контраст)

> **Оговорка (N6, 2026-07-16):** таблица — emulation-запись и формат FM2. **RAM-probe @ mf=8** сейчас PASS у native/synthetic/pipeline, но **ложноположителен для PPU** (на экране title при `x=129`). Критерий эфира — **визуальный** gameplay (§ «Визуальная проверка playback»).

| Компонент | Статус | Доказательство |

| --------- | ------ | -------------- |

| Запись inference (`run_inference.py`) | OK **только emulation** | bridge: `-loadstate inference_cp0.fc0`; метрики `max_cp=4`, reward ≈497 |

| Экспорт FM2 | OK **формат + RAM-probe** | `savestate 0x…`, GUID; **PPU replay — FAIL** (title @ mf=8, § visual) |

| Staging playback | OK | `refresh_fm2_embedded_savestate` из `inference_cp0`, `stage_playback_fc0`, mirror в `fcs/` |

| Плейлист / dedupe | OK | `fm2_path`, `remap_fm2_guid` |

| Lua overlay / HUD | OK | achievement overlay, диагностика `boot=…` |

| **Визуальный FM2 replay (win64 GUI)** | **FAIL** | title @ mf=8 при `gameplay_like_ram=true` (native, pipeline, staged); § visual |



---



## Корневая причина (уточнённая, 2026-07-16)



**Три слоя (после N6 + visual):**



1. **Данные / embed (гигиена закрыта):** GUID @5699, `refresh_fm2_embedded_savestate`, stale blob — лечится staging; **не объясняет** PPU title (staging vs raw визуально идентичны).

2. **RAM↔PPU desync в movie readonly (основной слой, открыт):** при `-playmovie -readonly 1` RAM может показывать gameplay-start (`x=129`, `room=0`), а **PPU — title** («1 PLAYER»). Воспроизводится на **native `movie.record`**, synthetic `build_empty_fm2` и pipeline `export_episode_fm2_from_steps` — § «Визуальная проверка playback». Критерий `gameplay_like_ram` **недостаточен** для закрытия issue.

3. **Контракт embed (вторичный, для фазы 3):** native пишет `savestate base64:` (FCSX ~4 KB), пайплайн — `savestate 0x:` (полный FCS ~79 KB). RAM-probe не различает; визуал @ mf=8 — одинаковый title. Фаза 3 — parity через `movie.record`.

**Режимы FCEUX:** bridge `-loadstate` при `run_inference` — RAM + PPU согласованы **в bridge**. Standalone GUI playback (`play_inference_fm2` + `achievement_overlay.lua`, CLI `-loadstate` без `savestate.load` bootstrap) — **PPU title/attract** при продолжении emulation (§ «BACKLOG 3.4»). Movie readonly — embed/Lua load **не синхронизирует PPU** с RAM (P7–P16).



Запись и просмотр — **разные контракты**:



| Режим | Старт | Визуал | RAM / метрики |

| ----- | ----- | ------ | ------------- |

| `run_inference` | bridge `-loadstate inference_cp0.fc0` | gameplay | валидны **в emulation**; экспорт FM2 → replay **не верифицирован** |

| `play_inference_fm2` (3.4) | emulation `-loadstate` + `inference_inputs.jsonl` | **title / attract** @ GUI f≈28 (оператор, 2026-07-16) | overlay OK; HUD `REPLAY/GAMEPLAY` **не отражает PPU** |
| `play_inference_fm2` (3.1–3.3, movie) | movie mode (`-playmovie` / Lua `movie.play`) | **title** @ mf=8 (visual) | RAM `x=129` возможен; **PPU ≠ RAM** (§ visual) |



---



## Отвергнутые гипотезы (ранние)



| ID | Гипотеза | Вердикт | Комментарий |

| -- | -------- | ------- | ----------- |

| H1 | FCEUX путает FM2 по GUID в `portable/movies/` | частично | Реальна при загрязнении `movies/`; **не объясняет** demo при пустой папке |

| H2 | Одинаковый GUID в плейлисте | исправлена | `remap_fm2_guid`; на картинку не влияет |

| H3 | Дедуп схлопывает клипы | неверна | digest кадров различается |

| H4 | Битый `fceux64.exe` | неверна | MD5 = донор 2.6.6 win64 |

| H5 | Шаблон в `portable/movies/` — причина demo | переоценена | Гигиена переноса в `reference/header.fm2` полезна, playback не лечит |

| H6 | Агент получает CP4 на title | неверна | CP на title невалидны; агент стартует с gameplay в **emulation** (не доказывает корректность FM2 export) |



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

| P24 | Replay через `FceuxBridge` + jsonl вместо FM2 | **отвергнута** — B0 operator FAIL (title → black); § B-proto |

| P25 | Pre-render MP4 для эфира вместо FM2 | **отвергнута** — FM2 нативен для FCEUX; видеофайлы тяжелее в хранении/пересылке (2026-07-16) |



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

| M2 | Ручная запись movie с середины игры: FCEUX вшивает `savestate` в FM2 без отдельного файла | **правдоподобна (FCEUX)** | → **§ F-proto** F1 (GUI / автоматизация); не опробована как путь эфира |



#### Ось «где сохранён» vs «где применён» (исследование пользователя)



| ID | Гипотеза | Вердикт | Проработка |

| -- | -------- | ------- | ---------- |

| M3 | FCS, снятый в **emulation mode**, **нельзя** применить для корректного **movie readonly** replay | **подтверждена (RAM); ось capture не уникальна** | § M-proto-1 шаги 3–5: gameplay-capture = inference_cp0 control на mf=8 |

| M4 | FCS, снятый при **movie playback**, **нельзя** применить в **emulation mode** | **опровергнута** | `inference_cp0` снят при проигрывании `clear.fm2`; `run_inference` (`-loadstate` без movie) — gameplay в **emulation** (не доказывает FM2 export) |

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

(clear.fm2)   → OK (emulation)   → RAM varies; PPU title @ mf=8 (N6 visual)

@ gameplay    не тестировали (F-proto)   не тестировали (F-proto)   § F-proto

              M-proto-1 @ mf=8 (утро): x=0; N6 (день): x=129 RAM, title PPU

@ same FM2    не тестировали      M6 **отвергнута**

mf=0          capture x=0 @ mf=1   нет улучшения

```



**Вывод по M3–M4 (исторический, M-proto):** на момент M-proto-1 probe @ mf=8 давал `x=0`. **N6 (2026-07-16, позже):** RAM `x=129` у native/synthetic/pipeline, но **PPU title** — см. § visual. Ось «где сохранён» не объясняет симптом полностью. Для `inference_cp0`: emulation OK; movie readonly — **RAM↔PPU desync**.



### Протокол проверки (оставшиеся M3, M6, N3)



#### § M-proto-1 — gameplay capture → movie readonly (M3)



| Шаг | Действие | Статус | Результат (2026-07-16) |
| --- | -------- | ------ | ---------------------- |
| 1 | ROM + `-loadstate inference_cp0`, **без** movie; проверка RAM | **OK** | emulation capture (одноразовый скрипт, удалён): `movie_active=false`, `room=0`, `x=129`, `lives=0` (эталон gameplay-start) |
| 2 | `savestate.save` при неактивном movie | **OK** | `tmp/bench/mproto1/gameplay_capture.fc0` (слот 0, emulation capture) |
| 3 | Тестовый FM2 с embed из шага 2 + 30–60 кадров | **OK** | `tmp/bench/mproto1/gameplay_capture.fm2`, `inference_cp0_control.fm2` (`build_empty_fm2`, 60 пустых кадров) |
| 4 | `-playmovie test.fm2 -readonly 1` + probe | **OK** | `movie_playback_probe.lua` @ mf=8: оба клипа `room=0`, `x=0`, `gameplay_like_ram=false` |
| 5 | Сравнение с контролем (`inference_cp0` embed) | **OK** | **Идентичный RAM** на mf=8; FCS различаются (68 байт), playback — нет |



**Вердикт M3 (2026-07-16):** gameplay-capture FCS **не** даёт gameplay RAM в movie readonly на **синтетических** FM2. Контроль (`inference_cp0` embed) ведёт себя **так же** — ось «где сохранён» **не объясняет** расхождение. Ранний вывод «проблема только в apply @ movie readonly FCEUX» **не учитывает** нативную запись (§ N6).

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
| Extract | side-by-side в `fceux/portable_github_v266/` (удалено после N2) |
| MD5 `fceux64.exe` | `a8a75e0a20627d822d467c46dee9744b` — **совпадает** с `fceux/portable/` |
| Probe @ mf=8 (`FCEUX_HOME=portable_github_v266`) | `room=0`, `x=0`, `gameplay_like_ram=false` — **как win64 portable** |

**Вывод:** официальный релиз GitHub **не отличается** от установленного portable; гипотеза «битый exe» (H4) подкреплена.

### FCEUX 2.2.2 win32 (SourceForge, 2026-07-16)

| Шаг | Результат |
| --- | --------- |
| Download | `tmp/bench/fceux-n2/fceux-2.2.2-win32.zip` |
| Extract | side-by-side в `fceux/portable_222_win32/` (удалено после N2) |
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

- **Standalone jsonl replay** (CLI `-loadstate` + `achievement_overlay.lua`, **3.4**) — **GUI FAIL**; не продолжать. Movie FM2 replay — вне inference-пайплайна до pass **§ F-proto**.

- Патч GUID в cross-movie FCS без movie-bound bootstrap (M5) — см. P1–P4



---



## Полезные изменения в ветке (оставить)



| Изменение | Зачем |

| --------- | ----- |

| `reference/header.fm2`, `default_fm2_template()` | артефакты в плагине |

| `ensure_savestate_movie_guid`, `refresh_fm2_embedded_savestate` | embed + GUID в файле (гигиена); **не** гарантия валидного movie replay (N6) |

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

| N4 | Smoke с `requires_fceux` + RAM probe @ gameplay | **RAM pass; PPU — нет** | `tests/test_fm2_playback_fceux.py`; нужен visual assert |

| N5 | Перезапись `ep*.fm2` из pipeline (embed при export, не только staging) | **закрыта (формат)** | embed в файле есть; staging не лечит PPU (§ visual) |

| — | Полный FM2 inference с power-on (M8) | **отвергнута** | M-proto: `clear.fm2` RAM `x=0` @ mf=18 |

| N6 | **Native record→play** vs synthetic export | **Ф0–2b + visual done** | RAM PASS @ mf=8; PPU title у всех; embed FCSX≠0x; § N6 |



---



## Текущий контракт кода (не закрывает issue)



```

staging: remap_fm2_guid → refresh embed from inference_cp0
CLI:     fceux -lua achievement_overlay.lua -playmovie playback.fm2 -readonly 1 rushn_attack
Lua:     диагностический HUD; без savestate bootstrap

```



**Фактический результат (2026-07-16):** PPU title @ mf=8; RAM может быть `x=129` (RAM↔PPU desync). См. таблицы P1–P24, § visual.



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

## Итоги исследования (2026-07-16, обновлено после N6 visual)



M/N-гипотезы и N6 фазы 0–2b проработаны. **Итоговая модель issue:**

- **Симптом эфира:** PPU title/black при movie playback (подтверждено screenshot @ mf=8).
- **RAM-probe `x=129`:** ложноположительный для PPU; N4 pass **не закрывает** issue.
- **Native vs pipeline bytes:** embed-формат различается (FCSX base64 vs 0x hex), но **не объясняет** визуальный симптом alone (оба — title @ mf=8).
- **Staging** (`remap_guid`, `refresh_embed`): на PPU не влияет.

**Хронология RAM @ mf=8:** M-proto-1 (утро) — `x=0`; N6 ф0–2b (день) — `x=129`; visual — title при обоих условиях.

| Что проверено | Вердикт |
| ------------- | ------- |
| GUID / embed / refresh (P1–P4, N5) | формат OK; staging не лечит PPU |
| gameplay vs movie capture (M3) | M-proto: RAM `x=0`; N6: RAM `x=129`, PPU title |
| movie-bound bootstrap (M6, N1) | отвергнута |
| fceux.cfg bind/full (N3) | без эффекта |
| FCEUX 2.6.6 GitHub / 2.2.2 win32 (N2) | тот же симптом (M-proto RAM) |
| power-on FM2 (M8, `clear.fm2`) | RAM `x=0` @ mf=18 (M-proto) |
| emulation `-loadstate` (`run_inference`, bridge) | **OK** в bridge | gameplay |
| jsonl replay GUI (`play_inference_fm2` 3.4) | **FAIL** (оператор) | **title / attract** @ f≈28; § 3.4 |
| N6 native / synthetic / pipeline | RAM PASS @ mf=8; **PPU title** (§ visual) |
| N6 visual @ mf=8 | native = pipeline = staged; **FAIL** gameplay PPU |

### Фактический контракт FCEUX (win64, 2026-07-16, после visual)

| Операция | Режим | RAM @ mf=8 | PPU @ mf=8 |
| -------- | ----- | ---------- | ---------- |
| Запись агента | bridge `-loadstate` | gameplay | gameplay |
| `movie.record` → play (N6-B) | movie readonly | `x=129` | **title** |
| Pipeline ep-FM2 | movie readonly | `x=129` | **title** |
| `play_inference_fm2` (staged) | movie readonly | `x=129` | **title** |
| Эфир (симптом issue) | movie readonly | может быть OK | **title / black** |

### Расхождение с BACKLOG 3.1–3.3

Критерий 3.1 («FM2 без `-loadstate`») **не соответствует цели** — плейлист попыток агента на эфире. Movie readonly даёт title при RAM bootstrap. Standalone jsonl (**3.4**) и bridge (**B0**) — FAIL на GUI. Следующий путь → **[BACKLOG 3.6](BACKLOG.md#36-inference-replay-fm2-gameplay-capture-f-proto)** § F-proto.

### N4 — автоматический критерий

```bash
./.venv/Scripts/python.exe -m pytest tests/test_fm2_playback_fceux.py -m requires_fceux
```

Тесты: RAM @ mf=8/18 + **PPU title_like @ mf=8** (`test_inference_embed_fm2_ppu_title_at_mf8`). При закрытии issue — инвертировать PPU assert (`title_like=False`).

### N5 — pipeline export

`run_inference` → `export_episode_fm2_from_steps` вшивает `savestate` при записи (`tests/test_fm2_export.py` — **только формат файла**, не round-trip). `play_inference_fm2.py` → `refresh_fm2_embedded_savestate` только в staging перед GUI; на PPU не влияет.

**Под сомнением (N6):** эквивалентность embed `0x` vs FCSX `base64` — для фазы 3; **не** объясняет PPU title @ mf=8.

### Что остаётся открытым

- **PPU gameplay** на **GUI эфире** — критерий закрытия issue; активный путь: **§ F-proto** / **[BACKLOG 3.6](BACKLOG.md#36-inference-replay-fm2-gameplay-capture-f-proto)**.
- **RAM↔PPU desync** в movie readonly — корневой слой; cross-movie embed из `inference_cp0` / pipeline **не лечит** (N6).
- **N4:** headless PPU @ frame 1 **ложноположителен** для GUI; gate — оператор @ mf=8, 28 (F-proto).
- **Visual sweep** @ mf 18,50,200,500 — **выполнен** (§ visual sweep); не отменяет проблему старта эфира.
- **BACKLOG [3.4](BACKLOG.md#34-плейлист-попыток-inference-replay)** — артефакты jsonl готовы; standalone replay **FAIL**.
- **BACKLOG [3.5](BACKLOG.md#35-inference-replay-bridge-playback-b-proto)** — **закрыт** (B0 FAIL); не продолжать.
- P18 — не приоритет.

---

## BACKLOG 3.4 — jsonl emulation replay (GUI эфир, 2026-07-16)

**Статус:** **закрыт (артефакты)** / **standalone replay FAIL** — jsonl + playlist готовы; GUI title @ f≈28. Визуальный replay → **[BACKLOG 3.6](BACKLOG.md#36-inference-replay-fm2-gameplay-capture-f-proto)** § F-proto (FM2-native).

### Что сделано (ветка `issue/inference-fm2-replay`)

| Компонент | Статус |
| --------- | ------ |
| `run_inference` | пишет `inference_inputs.jsonl`, без FM2 export |
| `build_playlist` / `playlist.json` | клип = episode + jsonl + overlay |
| `play_inference_fm2.py` | emulation + jsonl, без `-playmovie` |
| `achievement_overlay.lua` | `registerbefore`/`registerafter`, joypad из jsonl |
| `export_fm2.py` | **удалён** из inference-пути |
| Headless probe | `inference_replay_visual_probe.lua` @ frame 1 — gameplay PPU PASS |
| Автотесты | `test_inference_replay_fceux.py`, `test_playback_overlay_fceux.py`, E2E `done.flag` |

### Симптом (оператор, GUI win64, 2026-07-16)

Запуск `20260716_playlist.play.cmd` / `play_inference_fm2.py`:

- На экране: **title Rush'n Attack** («PLAY SELECT», «1 PLAYER»), attract demo — **не геймплей уровня**.
- Overlay: **корректен** (номинация `Almost finish`, CP:4, R:498, steps:400).
- HUD: `REPLAY/GAMEPLAY f≈28 r=0x00 L=0` — **метка скрипта**, не верификация PPU.
- Replay **идёт** (счётчик кадров растёт, `done.flag` пишется, E2E PASS по времени).

Ранее на этой ветке: **серый экран** (синхронный `emu.frameadvance()` + безусловный `nothrottle` в overlay) — исправлен возвратом register-hooks; после фикса — **title**, не gameplay.

### Headless vs GUI (расхождение приёмки)

| Проверка | Результат | Ловит GUI? |
| -------- | --------- | ---------- |
| `probe_inference_replay_ppu` @ frame 1 | gameplay PPU PASS | **нет** — снимок до joypad / sync-loop |
| `probe_playback_overlay_ppu` @ frame 1 (`probe_only`) | gameplay PPU PASS | **нет** — снимок сразу после CLI `-loadstate` |
| `probe_*` @ frame 8 (emulation) | title-like | частично; не тот бинарь, что GUI |
| `probe_*` @ frame 200 | gameplay PPU PASS | mid-episode; не лечит старт эфира |
| E2E `done.flag` + wall time | PASS | **нет** — не смотрит в окно |
| **Оператор GUI** | **title @ f≈28** | **да** |

**Вывод:** критерий закрытия issue — **только визуальная проверка GUI** (`achievement_overlay.lua`, `noicon=False`). RAM-probe и headless gdscreenshot **недостаточны**.

### Гипотезы (не исправлялись в этой сессии)

| ID | Гипотеза | Комментарий |
| -- | -------- | ----------- |
| J1 | CLI `-loadstate` без bridge-bootstrap (`savestate.save`→`savestate.load`) | bridge при `reset_to_state` делает CACHE+LOAD; overlay — только CLI `-loadstate` |
| J2 | PPU уходит на title через 1–2 кадра после loadstate | headless: frame 1 gameplay, frame 2+ title-like при тех же RAM |
| J3 | HUD `REPLAY/GAMEPLAY` вводит в заблуждение | флаг `replay_done`, не эвристика PPU |
| J4 | Replay через standalone FCEUX+Lua ≠ bridge emulation | `run_inference` OK; эфир — другой бинарь/путь |

### Направления (статус 2026-07-16)

| # | Идея | Статус |
| - | ---- | ------ |
| 1 | Bootstrap `savestate.load` в overlay (J1) | **отвергнуто** — standalone исчерпан (3.4 FAIL, B0 FAIL) |
| 2 | GUI smoke @ f=8..30 | **→ F-proto** (обязательный gate) |
| 3 | HUD: показывать `x` | опционально |
| 4 | Playback через `FceuxBridge` step | **отвергнуто** — B0 FAIL (§ B-proto) |

### Команды воспроизведения (3.4)

```bash
# Эфир (симптом — смотреть в окно FCEUX)
./.venv/Scripts/python.exe scripts/play_inference_fm2.py \
  games/rushn_attack/missions/m1/logs/YYYYMMDD_playlist.json --skip-preflight

# Headless (может PASS при том же баге GUI)
./.venv/Scripts/python.exe scripts/inference_replay_visual_check.py \
  --inputs games/rushn_attack/missions/m1/logs/YYYYMMDD_inference_inputs.jsonl \
  --episode 1 --probe-at-frame 1

./.venv/Scripts/python.exe -m pytest tests/test_playback_overlay_fceux.py tests/test_inference_replay_fceux.py -m requires_fceux
```

---

## N6 — Native record vs synthetic export

**Дата фиксации:** 2026-07-16  
**Статус:** **фазы 0–2b + visual sweep выполнены**. Закрытие issue → **§ F-proto** / **[BACKLOG 3.6](BACKLOG.md#36-inference-replay-fm2-gameplay-capture-f-proto)**. Harness N6 — диагностика movie mode.

### Гипотеза (историческая → пересмотр после visual)

| Наблюдение | Вывод |
| ---------- | ----- |
| GUI: Record input → Play Movie | Клип воспроизводится **как записан** (ожидание; сверить с автоматическим probe) |
| Пайплайн: `run_inference` → `export_episode_fm2_from_steps` → `play_inference_fm2` | **PPU title** @ mf=8; RAM `x=129` (N6 visual) |
| M2 (ручная запись с savestate) | Правдоподобна, **не автоматизирована** |
| M-proto-1/2 | Ранний RAM `x=0` на synthetic; N6 — RAM `x=129`, PPU title |
| N6 фаза 0 (2026-07-16) | `movie.record(save_type=1)` → RAM **PASS** @ mf=8; **PPU title** (§ visual) |

**Актуальная формулировка:** симптом — **RAM↔PPU desync** в movie readonly, не различие «native работает / synthetic ломает». Embed FCSX base64 (native) vs `0x` hex (pipeline) — вторичный слой (фаза 3). Критерий закрытия — **визуальный** gameplay-start.

### Два контракта (запись)

| | GUI / `movie.record` | Пайплайн |
| --- | --- | --- |
| Режим | Movie **record** | Emulation **без** movie |
| Старт | Start / Now / `.fc0` — FCEUX фиксирует state сессии | `bridge -loadstate inference_cp0` |
| Inputs | В movie в реальном времени | `step_log` → `fm2_frame_line` после эпизода |
| Embed | FCEUX вшивает при `movie.record(..., save_type)` | `build_fm2_header` + `inference_cp0` + `ensure_savestate_movie_guid` |
| Проверка «правильно пишем» | Round-trip record→play | Только метрики emulation + тесты формата файла |

### API FCEUX (программный путь вне пайплайна)

Документация: [Lua Functions List — movie](https://fceux.com/web/help/LuaFunctionsList.html).

| API | Назначение | Аналог GUI |
| --- | ---------- | ---------- |
| `movie.record(path, save_type, author)` | начать запись | Record input |
| `movie.stop()` | завершить запись | Stop recording |
| `movie.play(path, read_only)` | воспроизведение | Replay Movie |
| `joypad.set(1, input)` | ввод при записи | клавиатура / bridge |
| `savestate.load(slot)` | state перед record | Record From `.fc0` / Now |

`save_type`: `0` = Start (power-on), `1` = savestate, `2` = SaveRAM.

В репо: **playback**-probe (`movie_playback_probe.lua`, `probe_movie_playback`); **record**-harness (`movie_record_replay_probe.lua`, `probe_native_record_replay`); **visual**-probe movie (`movie_playback_visual_probe.lua`); **jsonl**-probe (`inference_replay_visual_probe.lua`, `scripts/inference_replay_visual_check.py`). Одноразовые `n6_phase*.py` CLI **удалены** (артефакты в `tmp/bench/fceux_native/`).

### Чистота эксперимента (фазы 0–2)

**Принцип:** сначала изолированно проверить **контракт FCEUX** (record→play), затем **минимум пайплайна**, и только после pass — achievements, эфир и staging. **Не приступать к выполнению** смешанных прогонов до явного старта N6.

#### Порядок проработки

| Этап | Что проверяем | Инструменты |
| ---- | ------------- | ----------- |
| **A** | API вне пайплайна | `movie.record` / `movie.play`, `movie_record_replay_probe.lua` |
| **B** | Минимум в пайплайне | `export_episode_fm2_from_steps` или `run_inference --episodes 1 --save-episode-fm2` **без** `--build-playlist`; probe через `probe_movie_playback` |
| **C** | Обвязка (только после pass A–B) | achievements, `.overlay.json`, `play_inference_fm2`, playlist, dedupe, именование `YYYYMMDD_ep*` |

Каждый слой этапа **C** — отдельный регрессионный шаг. Visual @ mf=8: staging **не** меняет PPU (raw = staged).

#### Вне scope фаз 0–2 (не подключать)

| Компонент | Почему мешает |
| --------- | ------------- |
| `play_inference_fm2.py` | `remap_fm2_guid`, `refresh_fm2_embedded_savestate` — меняет FM2 перед playback (P1–P4 уже крутили) |
| `achievement_overlay.lua` | HUD/overlay; для probe достаточно `movie_playback_probe.lua` |
| `evaluate_records` / tags | не в байтах FM2, но тянет sidecar и смешивает критерии |
| `build_playlist` / dedupe | копии FM2, новые GUID, номинации |
| `write_fm2_artifacts` / `.overlay.json` | sidecar не в заголовке FM2, но лишняя переменная на ранних фазах |
| Правки `refresh_fm2_embedded_savestate` / GUID «для лечения» | маскируют разницу native vs synthetic |

#### Минимальный чистый probe (эталон для A–B)

- **Запись:** `movie.record` (фаза 0) или один вызов `export_episode_fm2_from_steps` (фаза 2).
- **Воспроизведение:** `probe_movie_playback` + `movie_playback_probe.lua` — CLI `-playmovie … -readonly 1`, **без** overlay.
- **Не использовать** для критерия pass/fail: `play_inference_fm2.py`.

#### Минимальный прогон пайплайна (этап B, после pass фазы 0)

```bash
./.venv/Scripts/python.exe src/stream/run_inference.py \
  --checkpoint m1_v0.zip --episodes 1 --save-episode-fm2 --skip-preflight
# без --build-playlist
```

Проверка: `probe_movie_playback` на `logs/YYYYMMDD_ep0001.fm2`. Артефакты bench — в `tmp/bench/`, не полагаться на очистку `inference_preflight`.

#### Гигиена окружения

- `fceux/portable/movies/` — пуст (preflight / `warn_portable_movies_pollution`).
- **Frame skip:** 4 NES-кадра на env step при сравнении с native record.
- **Headless probe** ненадёжен (P22); фаза 0 — окно или `gui.savescreenshot`.

#### Этап C — порядок включения (после pass A–B)

1. `.overlay.json` / `write_fm2_artifacts`
2. `play_inference_fm2.py` (staging + overlay)
3. `eval_achievements` + tags в `attempts.jsonl`
4. `build_playlist` + dedupe + `YYYYMMDD_playlist.json` / `.play.cmd`

### Протокол (поэтапно)

Артефакты: `tmp/bench/fceux_native/` (`artifact_quarantine_dir("bench", "fceux_native")`). Одноразовые harness — удалять после фиксации JSON; не писать в `games/.../logs/` / `checkpoints/`.

#### Фаза 0 — Baseline native round-trip (**RAM PASS**, PPU FAIL @ mf=8, 2026-07-16)

**Цель:** доказать record→play с gameplay-start **вне** `fm2_export` / `run_inference`.

| Шаг | Действие | Статус | Результат |
| --- | -------- | ------ | --------- |
| 0.1 | ROM + `-loadstate inference_cp0.fc0` + Lua harness | **OK** | `room=0`, `x=129`, `gameplay_like_ram=true`, `movie_active=false` |
| 0.2 | `movie.record(out.fm2, 1)` + 60 кадров `joypad.set` (пустой ввод) | **OK** | `movie_mode=record` |
| 0.3 | `movie.stop()` | **OK** | `native_phase0.fm2`, 7147 B |
| 0.4 | `movie.play(out.fm2, true)` + RAM-probe @ mf=8 | **OK** | `x=129`, `gameplay_like_ram=true` |
| 0.4b | `probe_movie_playback` (CLI `-playmovie`) на том же FM2 | **OK** | идентичный RAM @ mf=8 |
| 0.5 | скриншот @ mf=8 | **FAIL** | title («1 PLAYER»); см. § «Визуальная проверка playback» |

**Вердикт фазы 0 (уточнённый):** RAM round-trip **PASS** (`x=129` @ mf=8) для native `movie.record(save_type=1)` после CLI `-loadstate inference_cp0`. **PPU @ mf=8 — title**, как у pipeline — § visual. Ранняя гипотеза «корень в сборке FM2, не в FCEUX» **снята**: native и synthetic/pipeline **одинаково** FAIL по PPU. Контраст M-proto-1 (`build_empty_fm2` → RAM `x=0`) — отдельная хронология условий.

Запуск (исторический; CLI `n6_phase0_native_record.py` удалён):

```bash
# Эквивалент: src/fm2_playback.probe_native_record_replay + tmp/bench/fceux_native/
```

Артефакты: `tmp/bench/fceux_native/phase0_result.json`, `native_phase0.fm2`.

```json
{
  "step_0_4": {"mf": 8, "room": 0, "x": 129, "gameplay_like_ram": true},
  "probe_movie_playback": {"mf": 8, "room": 0, "x": 129, "gameplay_like_ram": true}
}
```

**Заметки:** `save_type=1` без отдельного `savestate.load` — достаточно CLI `-loadstate`. Окно FCEUX (без `-noicon`); headless не тестировался на фазе 0.

#### Фаза 1 — Матрица Record From (**PASS**, 2026-07-16)

Тот же harness, три варианта `save_type` / подготовки:

| ID | Вариант | Подготовка | `movie.record` | embed | `is_from_savestate` | probe @ mf=8 |
| -- | ------- | ---------- | -------------- | ----- | ------------------- | ------------ |
| N6-A | Start | power-on | `save_type=0` | нет (1665 B) | false | `x=0` (title; ожидаемо) |
| N6-B | Now | CLI `-loadstate inference_cp0` | `save_type=1` | `savestate base64:` (~4096 B decoded) | true | **`x=129` PASS** |
| N6-C | Browse `.fc0` | `fcs/{rom}.fc0` → `savestate.create(1); load` | `save_type=1` | `savestate base64:` (~4089 B) | true | **`x=129` PASS** |

Запуск (исторический; CLI удалён):

```bash
# Артефакты: tmp/bench/fceux_native/phase1_results.json
```

Артефакты: `tmp/bench/fceux_native/phase1_results.json`, `native_n6-{a,b,c}.fm2`.

**Вердикт фазы 1:**

- **N6-B ≡ N6-C** для gameplay replay: оба дают `gameplay_like_ram=true` @ mf=8; embed чуть отличается по размеру (7135 vs 7147 B), формат одинаковый (`savestate base64:`).
- **N6-A** — power-on без embed; probe @ mf=8 на title (`x=0`) — контроль, не критерий inference.
- Нативный embed **не** `savestate 0x…` (синтетика пайплайна) — **`savestate base64:…`**; `fm2_has_embedded_savestate()` в репо **не видит** native embed без доработки (важно для фазы 2 diff).
- N6-C: `savestate.load` требует **handle** `savestate.create(slot+1)`, не номер слота напрямую.

#### Фаза 2 — Synthetic vs native (**выполнена**, 2026-07-16)

| Шаг | Действие | Результат |
| --- | -------- | --------- |
| 2.1 | Inputs из `native_n6-b.fm2` (60 кадров, пустой joypad) | `all_empty=true` |
| 2.2 | `build_empty_fm2` + embed `inference_cp0` | `synthetic_phase2.fm2` |
| 2.3 | `probe_movie_playback` @ mf=8 | **оба PASS** `x=129` |
| 2.4 | Diff заголовка / кадров | см. ниже |

Запуск (исторический; CLI удалён):

```bash
# Артефакты: tmp/bench/fceux_native/phase2_results.json
```

Артефакты: `tmp/bench/fceux_native/phase2_results.json`, `synthetic_phase2.fm2`.

**Diff (native N6-B vs synthetic):**

| Поле | Native | Synthetic |
| ---- | ------ | --------- |
| Кадры (60) | `\|0\|........\|........\|\|` | **идентичны** |
| `guid` | per-record | `episode_fm2_guid` |
| Embed формат | `savestate base64:` (FCSX, **4096 B**) | `savestate 0x:` (raw FCS, **79305 B**) |
| `embed_sha256` | ≠ | ≠ (разные blob) |
| RAM @ mf=8 | `x=129` PASS | `x=129` PASS |

**Вердикт фазы 2 (уточнённый):**

- Гипотеза «синтетика FAIL / native PASS» на **RAM-probe** — **не воспроизведена** (оба PASS). Это расходится с § M-proto-1 (`x=0` на `build_empty_fm2` 2026-07-16) — вероятно смена условий или состояния `inference_cp0`/FCEUX; требует отдельной сверки, если снова появится `x=0`.
- **Подтверждено:** пайплайн и native пишут **разный контракт embed** (сжатый FCSX+base64 vs полный FCS+hex) при **одинаковых** frame lines.
- Pipeline `logs/*_ep0001.fm2` @ mf=8 (2026-07-16): **RAM PASS** `x=129` через `probe_movie_playback` (без staging `play_inference_fm2`).
- Issue **не закрыт** по чеклисту: **визуальный** gameplay-start (PPU) и эфир через `play_inference_fm2` — отдельно от RAM-probe (P22).

**Следующий шаг:** visual sweep @ mf>8; фаза 3 (`movie.record` с FCSX embed); сверка ручного GUI record→play.

#### Фаза 2b — Минимум пайплайна (**PASS**, 2026-07-16)

| Шаг | Действие | Результат |
| --- | -------- | --------- |
| 2b.1 | `run_inference --episodes 1 --save-episode-fm2 --skip-preflight` | `logs/20260716_ep0001.fm2` (817 steps, 3268 frames, 234 KB) |
| 2b.2 | `probe_movie_playback` @ mf=8 | **`x=129` PASS** |
| 2b.3 | Сравнение с native/synthetic ф2 | RAM идентичен; embed pipeline = `0x` 79305 B (как synthetic), ≠ native FCSX 4 KB |

Запуск (исторический; CLI удалён):

```bash
# Артефакты: tmp/bench/fceux_native/phase2b_results.json
```

Артефакты: `tmp/bench/fceux_native/phase2b_results.json`, `games/…/logs/20260716_ep0001.fm2`.

Эпизод: `max_cp=4`, `reward≈456`, `died=True`, tags `deep_run`. Sidecar `.overlay.json` создаётся автоматически (`write_fm2_artifacts`) — на байты FM2 probe не влияет.

**Вердикт 2b:** минимальный пайплайн `export_episode_fm2_from_steps` → `probe_movie_playback` — **RAM PASS**. Контракт embed совпадает с синтетикой (`0x`), не с native (`base64` FCSX). Issue остаётся открытым по **визуальному** критерию — см. § «Визуальная проверка playback».

#### Визуальная проверка playback (**FAIL** @ mf≤50, **частичный PASS** @ mf≥200, 2026-07-16)

Скриншот PPU @ mf (`gui.gdscreenshot` → PNG) при `probe_movie_playback` / staging `play_inference_fm2`:

```bash
# Movie FM2 visual (pytest):
./.venv/Scripts/python.exe -m pytest tests/test_fm2_playback_fceux.py -k visual -q

# Jsonl emulation (BACKLOG 3.4):
./.venv/Scripts/python.exe scripts/inference_replay_visual_check.py \
  --jsonl games/rushn_attack/missions/m1/logs/20260716_inference_inputs.jsonl
```

##### mf=8 (исходная фиксация)

| Кейс | RAM @ mf=8 | PPU @ mf=8 | MSE vs native |
| ---- | ---------- | ---------- | ------------- |
| native N6-B | `x=129` PASS | **title** («1 PLAYER») | 0 |
| pipeline raw | `x=129` PASS | **title** | 54.84 |
| pipeline staged (`play_inference_fm2`) | `x=129` PASS | **title** | 54.84 |

Артефакты: `tmp/bench/fceux_visual/visual_*_mf8.png`, `visual_playback_results.json`.

##### Visual sweep (длинный ep `20260716_ep0001.fm2`, 3268 frames)

| mf | Кейс | RAM | PPU | Примечание |
| -- | ---- | --- | --- | ---------- |
| 18 | native N6-B / pipeline | `x=129` PASS | **title** | MSE native↔pipeline ≈16 |
| 50 | native N6-B / pipeline | `x=129` PASS | **title** | title держится ≥50 кадров |
| 200 | pipeline raw / staged | `x=155` | **gameplay** (мост, HUD) | RAM уже не bootstrap |
| 500 | pipeline raw / staged | `x=5` | **gameplay** | агент в уровне |

Артефакты sweep: `tmp/bench/fceux_visual/visual_playback_sweep.json`, `visual_*_mf{18,50,200,500}.png`.

**Вывод sweep:**

1. **Симптом эфира — front-loaded:** первые ~50 movie-кадров PPU = title, RAM = bootstrap `x=129` (ложноположительный RAM-probe). С mf≈200 inputs «догоняют» — на экране gameplay, RAM = реальная позиция (`x≠129`).
2. **Native N6-B ≡ pipeline @ mf≤50:** оба title при `x=129` — **не** различие synthetic vs native embed.
3. **Ручной GUI record→play (N6-B):** автоматический harness (`movie.record(save_type=1)` + CLI `-loadstate inference_cp0`) **эквивалентен** контракту GUI «Record From Now»; сверка @ mf=18/50 даёт тот же title. Ручной прогон в GUI — опциональная верификация, ожидается идентичный результат.
4. **Фаза 3 (`movie.record` + FCSX embed)** **не устраняет** title @ mf≤50: native уже пишет FCSX base64 и FAIL по PPU на старте.
5. **BACKLOG 3.4:** embed FM2 + `-playmovie` **убрать** из inference-пайплайна; replay = emulation + `inference_inputs.jsonl`.

**N4 PPU-assert:** `test_inference_embed_fm2_ppu_title_at_mf8` — фиксирует title @ mf=8 при RAM pass; при закрытии issue инвертировать assert (`title_like=False`).

#### Фаза 3 — снята

N6 фаза 3 (`movie.record` в пайплайне) **не лечит** title @ mf≤50. Standalone jsonl (**3.4**) и bridge (**B0**) — FAIL на GUI. Следующий путь → **§ F-proto** / **[BACKLOG 3.6](BACKLOG.md#36-inference-replay-fm2-gameplay-capture-f-proto)**.

### Компоненты N6 (репо)

| Компонент | Назначение |
| --------- | ---------- |
| `fceux/lua/movie_record_replay_probe.lua` | record → stop → play → RAM-probe; config через `WAIT_FCEUX_LUA_CONFIG` |
| `src/fm2_playback.probe_native_record_replay` | Python: staging, subprocess, чтение result JSON |
| `tests/test_fm2_playback_fceux.py` | pytest: native record, movie playback visual |
| `scripts/inference_replay_visual_check.py` | CLI: jsonl emulation visual @ gameplay frame |
| `fceux/lua/movie_playback_visual_probe.lua` | RAM + `gdscreenshot` probe (movie) |
| `tmp/bench/fceux_native/*.json` | результаты фаз 0–2 |

CLI record (без `-playmovie` на старте):

```bash
fceux64.exe -noicon 1 -turbo 1 -nothrottle 1 \
  -lua fceux/lua/movie_record_replay_probe.lua \
  -loadstate inference_cp0.fc0 \
  rushn_attack.nes
```

### Ограничения / заметки

- **Frame skip:** inference = 4 NES-кадра на env step; в native record явно подавать 4 кадра на action.
- **Headless:** probe без GUI ненадёжен (P22); фаза 0 — с окном или скриншот.
- **`save_type=1`:** CLI `-loadstate` (N6-B) или `savestate.create(slot+1); load` (N6-C) — оба **PASS** @ mf=8.
- **Не смешивать** с правками `refresh_fm2_embedded_savestate` / GUID до завершения фазы 2.
- **Фазы 0–2 / 2b:** achievements, playlist, `play_inference_fm2` — вне scope (§ «Чистота эксперимента»).

---

## B-proto — bridge playback (2026-07-16)

**Статус:** **B0 FAIL** (оператор 2026-07-16) — гипотеза B0 **отвергнута**; B1/C не начинать  
**BACKLOG:** [3.5](BACKLOG.md#35-inference-replay-bridge-playback-b-proto)  
**Принцип:** как N6 — сначала вне пайплайна, gate = **GUI оператор**; pass → внедрение; fail → зафиксировать отвержение. **Не** pre-render MP4 (P25).

### Гипотеза B0

Replay через `FceuxBridge.reset_to_state("states/inference_cp0.fc0")` + `bridge.step(action)` по actions из jsonl даёт **тот же PPU**, что `run_inference` (gameplay @ f=8, 28), в отличие от standalone CLI `-loadstate` + `achievement_overlay.lua` (FAIL @ f≈28, J4).

### Закрытые пути (не продолжать)

| Путь | Вердикт | Ссылка |
| ---- | ------- | ------ |
| FM2 + `-playmovie` | отвергнут | N6 visual |
| Standalone emulation + jsonl (3.4) | **GUI FAIL** | § BACKLOG 3.4 |
| Bridge reset + step (B0/B1) | **отвергнут** | B0 operator FAIL |
| Pre-render MP4 (эфир) | **отвергнут** | P25; FM2 — целевой формат |
| J1 bootstrap в overlay без B0 | отложено | ниже приоритет |

### Протокол

Артефакты: `tmp/bench/bridge_playback/` (`artifact_quarantine_dir("bench", "bridge_playback")`).

#### Фаза B0 — минимальный bridge (вне пайплайна)

| Шаг | Действие | Критерий |
| --- | -------- | -------- |
| B0.1 | `FceuxBridge(show_window=True)`, `reset_to_state(inference_cp0)` | RAM: `room=0`, `x=129` |
| B0.2 | 60× `step("")` (frame_skip=4) | RAM стабилен |
| B0.3 | Скриншот / obs @ NES f=8, 28 | PPU heuristic (вспомогательно) |
| B0.4 | **Оператор** смотрит окно @ f=8, 28 | **PASS/FAIL gate** |

**Вне scope:** `play_inference_fm2.py`, `achievement_overlay.lua`, playlist, FM2.

#### Фаза B1 — реальный jsonl

| Шаг | Действие |
| --- | -------- |
| B1.1 | `episode_step_actions(jsonl, episode=1)` → `bridge.step(action)` |
| B1.2 | Скриншоты @ f=8, 28, 200 |
| B1.3 | Оператор @ f=8, 28 |

#### Фаза B2 — сверка с записью (опц.)

`run_inference --episodes 1` → replay того же episode через bridge → сравнение RAM по steps.

#### Фаза C — внедрение (только после pass B0+B1)

1. Backend в `play_inference_fm2.py` (FM2-native), playlist, overlay

### Вердикты (заполнять по ходу)

| Фаза | Дата | Вердикт | Артефакт |
| ---- | ---- | ------- | -------- |
| B0 | 2026-07-16 | **FAIL** (оператор) | `b0_results.json` |
| B1 | | *отменена* (B0 fail) | |
| B2 | | *отменена* | |
| C | | *отменена* | |

**Наблюдение оператора (B0.4):** после `reset_to_state(inference_cp0)` на PPU — **title** («Rush'n Attack», «1 PLAYER»), не gameplay; во время `HOLD` (8 с) — **чёрный экран** (attract). RAM @ reset: `room=0`, `x=129` (gameplay_like). **Вывод:** bridge playback **не даёт** gameplay PPU @ gameplay-start; гипотеза B0 ложна (PPU = title, как movie/standalone; RAM-probe ложноположителен). **Не внедрять** bridge backend в `play_inference_fm2.py`. **Целевой формат эфира остаётся FM2**; новые гипотезы — только FM2/FCEUX-native (не MP4, не jsonl-bridge).

**При FAIL B0:** записать наблюдение; не внедрять в пайплайн. Pre-render MP4 **не рассматривать** (P25). Следующий путь → **§ F-proto** / **[BACKLOG 3.6](BACKLOG.md#36-inference-replay-fm2-gameplay-capture-f-proto)**.

### Команды (история B0)

Артефакт вердикта: `tmp/bench/bridge_playback/b0_results.json` (2026-07-16). Harness удалён после FAIL.

---

## F-proto — FM2 gameplay capture (M2 / capture @ gameplay, 2026-07-16)

**Статус:** **активный** — следующая FM2-гипотеза после отвержения B0 / 3.4 standalone  
**BACKLOG:** [3.6](BACKLOG.md#36-inference-replay-fm2-gameplay-capture-f-proto)  
**Принцип:** как N6 — сначала изолированный bench вне пайплайна; gate = **GUI оператор** @ mf=8, 28; pass → внедрение в `play_inference_fm2.py` / playlist FM2.

### Корневая гипотеза

**Cross-movie embed** (файл `inference_cp0.fc0`, снятый при playback `clear.fm2`, вшитый в FM2 попытки агента) даёт **RAM↔PPU desync** при `-playmovie`: RAM gameplay_like, PPU title/black.  
**Capture @ gameplay в emulation** (movie inactive) и вшивание **movie-bound** FCS в FM2 — ещё **не тестировали** (таблица M3, строка `@ gameplay`).

| ID | Формулировка | Отличие от отвергнутого |
| -- | ------------ | ----------------------- |
| **F0** | Emulation: `savestate.save` @ gameplay → `movie.record(save_type=1)` с load слота **до** record | N6-B: только CLI `-loadstate` файл; N6-C: mirror fc0→fcs, не in-session capture |
| **F1** | M2: нативная запись FM2 «с середины» без внешнего `.fc0` (FCEUX embed в movie) | альтернатива pipeline `0x` + jsonl-export |
| **F2** | Сравнение FCSX (native) vs `0x` (pipeline) | только если F0/F1 дают иной RAM/PPU, чем N6 |

**Не продолжать:** bridge step replay (B0), standalone jsonl (3.4), pre-render MP4 (P25), правки `bridge.lua` train IPC.

### Протокол

Артефакты: `tmp/bench/fm2_gameplay_capture/` (`artifact_quarantine_dir("bench", "fm2_gameplay_capture")`).

#### Фаза F0 — emulation capture → native record

| Шаг | Действие | Критерий |
| --- | -------- | -------- |
| F0.1 | ROM + CLI `-loadstate inference_cp0` (bootstrap RAM) | RAM: `room=0`, `x≈129` |
| F0.2 | Lua: `savestate.create` + `savestate.save` в **emulation** (movie inactive) | slot готов |
| F0.3 | `movie.record(save_type=1)` + `savestate.load(slot)` **до** первого input frame | FM2 с FCSX embed |
| F0.4 | Record N пустых / jsonl frames → stop → `-playmovie` readonly | RAM-probe вспомогательно |
| F0.5 | **Оператор** @ mf=8, 28 | **PASS/FAIL gate** |

Harness: расширить `movie_record_replay_probe.lua` (variant `F0`) + `probe_native_record_replay` в `fm2_playback.py`; pytest `test_fm2_playback_fceux.py` (`requires_fceux`).

**Наблюдение оператора (F0.5, 2026-07-16):** emulation capture (`savestate.save` @ gameplay, movie inactive) → `movie.record(save_type=1)` + load слота → readonly play. RAM @ mf=8/28: `room=0`, `x=129` (**PASS**). PPU @ mf=8 и mf=28: **title** («1 PLAYER»), `title_like=true` — **FAIL** gate. Embed FCSX ~4089 B (in-session capture, не cross-movie файл). **Вывод:** in-session gameplay capture **не лечит** RAM↔PPU desync; симптом **идентичен N6-B**. F1 — только если нужна альтернатива pipeline `0x` (опц.).

#### Фаза F1 — M2 «Record From Now» (опц. после F0)

| Шаг | Действие |
| --- | -------- |
| F1.1 | Дойти до gameplay (loadstate или attract skip) в **GUI** |
| F1.2 | `movie.record` mid-game без внешнего `.fc0` |
| F1.3 | Короткий клип → readonly play → оператор @ mf=8, 28 |

Автоматизация F1 — только если F0 даёт сигнал (PASS или отличимый от N6-B RAM/PPU).

#### Фаза F2 — embed format (только при необходимости)

Сравнить FCSX в FM2 (F0) с `build_empty_fm2` + pipeline `0x` на том же теле movie.

#### Фаза C — внедрение (только после pass F0 + оператор)

1. Export FM2 в inference-пайплайне с gameplay-bound embed (не cross-movie `inference_cp0` файл).
2. `play_inference_fm2.py` / playlist: `-playmovie` без CLI `-loadstate`.
3. Overlay (OBS или achievement) — отдельно; не блокирует F0 gate.

### Вердикты (заполнять по ходу)

| Фаза | Дата | Вердикт | Артефакт |
| ---- | ---- | ------- | -------- |
| F0 | 2026-07-16 | **FAIL** (оператор) — ложный `inference_cp0` (title); см. **§ G0** | `f0_results.json` |
| F1 | | superseded by G0 | |
| F2 | | superseded by G0 | |
| C | 2026-07-16 | **C1–C3 PASS** — issue закрыт | § фаза C |
| **G0** | 2026-07-16 | **PASS** — корень = bad gameplay_start; FM2 OK с FCS @1250 | `tmp/bench/gameplay_fix_g0/` |

### Вне scope F-proto

| Компонент | Почему |
| --------- | ------ |
| `play_inference_fm2.py` (prod path) | до pass F0 / G0 rebuild |
| `FceuxBridge` step replay | B0 отвергнут |
| `achievement_overlay.lua` standalone | 3.4 FAIL |
| Pre-render MP4 | P25 отвергнут |
| Правки train `bridge.lua` | риск регрессии 1.9 |

### Команды (черновик)

```bash
# после реализации harness F0:
./.venv/Scripts/python.exe -m pytest tests/test_fm2_playback_fceux.py -k F0 -v
# артефакты: tmp/bench/fm2_gameplay_capture/
```

---

## G0 — ложный gameplay_start (2026-07-16)

**Вердикт:** **PASS (корень найден и подтверждён harness + скриншотами).**

### Симптом, переинтерпретированный

«RAM↔PPU desync» в N6/F0 **не** баг FCEUX movie embed. Критерий `gameplay_like_ram = (room==0 && x==129)` совпадает с **title/attract** Rush'n Attack (`lives=0`). `inference_cp0` снят на кадре **18** эталона — там уже `room=0x00,x=129`, но на экране «1 PLAYER».

| Артефакт | lives | PPU |
| -------- | ----- | --- |
| Старый `inference_cp0` @18 | 0 | **title** |
| FCS @ clear mf=1250 | 6 | **gameplay** (мост) |
| Synthetic FM2 + embed @1250 | 6 | **gameplay @ mf=8** |
| Native `movie.record` от FCS @1250 | 6 | **gameplay @ mf=8** |
| FCS @1226 (lives-only heuristic) | 5 | **чёрный** (fade room 0x11→0x01) |

`clear.fm2` сам по себе валиден: gameplay на экране с ~mf=1500; title до ~mf=200 — нормальный intro.

### Исправление

1. `gameplay_start_frame_from_rows`: `room ∉ transition` **и** `lives ∈ [1,9]` **и** movement/attack input (не fade @1226).
2. `scripts/build_inference_states.py` → `gameplay_start_frame: 1250`, новый `states/inference_cp0.fc0`.
3. Lua probes: `gameplay_like_ram = (lives >= 1 and lives <= 9)`.
4. Pytest: `test_inference_embed_fm2_ppu_gameplay_at_mf8` — **PASS** (title_like=False).
5. Дальше: фаза **C** (ниже) — внедрение в pipeline.

Артефакты: `tmp/bench/gameplay_fix_g0/g0_results.json`, `emu_real_gp.png`, `syn_real_mf8.png`, `native_real_mf8.png`.

---

## Фаза C — внедрение FM2 в pipeline (после G0)

**BACKLOG:** [3.6](BACKLOG.md#36-inference-replay-fm2-gameplay-capture-f-proto)  
**Принцип:** поэтапно; каждый этап заканчивается **командой для визуального теста оператором** (окно FCEUX, gameplay с mf≈8). Embed = `states/inference_cp0.fc0` @1250 (файл с диска OK после G0).

| Этап | Что | Gate (оператор) | Статус |
| ---- | --- | --------------- | ------ |
| **C1** | `export_fm2` + `run_inference --save-episode-fm2`; `play_fm2_gui.py` | один `.fm2` → gameplay PPU | **PASS** (оператор 2026-07-16) |
| **C2** | `play_inference_fm2.py` → `-playmovie` + `achievement_overlay_movie.lua` | тот же клип + overlay | **PASS** (оператор 2026-07-16) |
| **C3** | `playlist.json` с `fm2`; launcher → `play_inference_fm2` | плейлист подряд | **PASS** (оператор 2026-07-16) |

### C1 — export FM2 (2026-07-16) — PASS

Код: `scripts/export_fm2.py`, `scripts/play_fm2_gui.py`, `run_inference --save-episode-fm2`.  
Оператор: `play_fm2_gui.py` → `20260716_ep0001.fm2` — gameplay (**PASS**).

### C2 — play_inference_fm2 movie path (2026-07-16) — PASS

Код: `scripts/play_inference_fm2.py` (`.fm2` → `-playmovie`), `fceux/lua/achievement_overlay_movie.lua`.  
Оператор: тот же `20260716_ep0001.fm2` — gameplay + overlay (**PASS**).

### C3 — playlist FM2 (2026-07-16) — PASS

Код: `src/achievements/playlist.py` — клипы `YYYYMMDD_NN_slug_NNN.fm2` + overlay; manifest с `"fm2"`; `.play.cmd` → `play_inference_fm2.py --skip-preflight`.  
Оператор: `20260716_playlist.play.cmd` — gameplay + overlay (**PASS**).

---

## Чеклист закрытия



- [x] **B-proto B0** — оператор GUI: **FAIL** — title @ reset, чёрный @ HOLD (2026-07-16); RAM `x=129` не отражает PPU
- [x] **B-proto B1** — **отменена** (B0 fail)
- [x] **F-proto F0** — emulation capture → native record; оператор GUI @ mf=8, 28 — **FAIL** на *старом* title-`inference_cp0` (объяснено G0)
- [x] **G0** — ложный `gameplay_start_frame=18`; rebuild @**1250**; FM2 embed PPU gameplay @ mf=8 (pytest PASS)
- [x] **C1–C3** — export / play_inference / playlist FM2 — оператор GUI PASS (2026-07-16)
- [x] N6 visual probe @ mf=8 — title на *старом* cp0; superseded by G0 + C

- [x] Visual sweep @ mf 18,50,200,500 на длинном ep (`20260716_ep0001.fm2`) — title ≤50, gameplay @200+; `visual_playback_sweep.json`

- [x] Контракт win64 документирован (§ «Фактический контракт FCEUX»)

- [x] Smoke `requires_fceux` с RAM assert (`tests/test_fm2_playback_fceux.py`; **pass** RAM, issue открыт по PPU)

- [x] BACKLOG 3.1 критерий уточнён под фактический контракт (§ «Расхождение с BACKLOG 3.1»)

- [x] M3 / § M-proto-1 — gameplay capture

- [x] M6 / § M-proto-2 — **отвергнута**

- [x] M8 — power-on FM2 — **отвергнута**

- [x] N3 / § M-proto-3 — **отвергнута**

- [x] N2 / § N2-proto — 2.6.6 + 2.2.2

- [x] ~~HUD `REPLAY/GAMEPLAY` **и** совпадение PPU~~ — **не блокер**; при bridge → OBS overlay

- [x] N4 — RAM smoke + PPU assert (`test_inference_embed_fm2_ppu_title_at_mf8` фиксирует title @ mf=8)

- [x] N5 — embed при export (**формат**; PPU не лечит)

- [x] N6 фаза 0 — native record→play (**RAM PASS**; PPU title @ mf=8; `phase0_result.json`)

- [x] N6 фаза 1 — матрица Record From (**PASS**, `tmp/bench/fceux_native/phase1_results.json`)

- [x] N6 фаза 2 — native vs `build_empty_fm2` (**RAM оба PASS**; embed FCSX≠0x; `phase2_results.json`)

- [x] N6 фаза 2b — минимум пайплайна (**PASS**, `phase2b_results.json`, `20260716_ep0001.fm2`)

- [x] Issue закрыт = **BACKLOG [3.6](BACKLOG.md#36-inference-replay-fm2-gameplay-capture-f-proto)** C1–C3 оператор PASS; ~~3.4 standalone~~ / ~~3.5 bridge~~ — FAIL, не критерий



---



## Ссылки на код



| Файл | Роль |

| ---- | ---- |

| `scripts/play_inference_fm2.py` | FM2 `-playmovie` + playlist; legacy jsonl |
| `src/inference_replay.py` | staging, `run_inference_playback`, visual probe |
| `fceux/lua/inference_replay_visual_probe.lua` | headless visual probe (sync loop) |
| `fceux/lua/achievement_overlay.lua` | overlay + jsonl joypad replay (GUI) |
| `scripts/inference_replay_visual_check.py` | CLI headless visual check |
| `scripts/inference_playlist_e2e.py` | E2E inference → playlist → play |
| `tests/test_inference_replay_fceux.py` | N4 jsonl replay (headless) |
| `tests/test_playback_overlay_fceux.py` | overlay hook smoke (headless) |
| `src/fm2_playback.py` | argv, staging helpers; movie probe (N6, не inference path) |
| `src/fm2_export.py` | embed, GUID; `export_fm2` / `--save-episode-fm2` |

| `games/…/states/inference_cp0.fc0` | gameplay-start state |

| `games/…/reference/human_playthrough.jsonl` | эталон room/x по кадрам |

| `src/stream/run_inference.py` | запись с bridge `-loadstate` |

| `fceux/lua/save_states.lua` | capture @ movie → `cp*.fc0` / `inference_cp0` |

| `fceux/lua/movie_playback_probe.lua` | RAM-probe при `-playmovie` (M-proto-1 шаги 4–5, N4) |

| `src/fm2_playback.probe_movie_playback` | Python-обёртка probe |

| `src/fm2_export.build_empty_fm2` | тестовые FM2 с embed (N4) |

| `src/fceux_bridge.py` | emulation mode: `-loadstate` без `-playmovie` |

| `tests/test_fm2_playback_fceux.py` | N4: RAM probe smoke (`requires_fceux`; **pass** RAM, не ловит PPU) |

| `fceux/lua/movie_playback_visual_probe.lua` | PPU screenshot + RAM @ mf (N6 movie, не 3.4) |

| `fceux/lua/movie_record_replay_probe.lua` | N6: native `movie.record` → play → probe |

| `src/fm2_playback.probe_native_record_replay` | N6 Python harness |

| `tmp/bench/fceux_native/` | N6 артефакты фаз 0–2 |

| `tmp/bench/fceux_visual/` | N6 visual screenshots + JSON |


