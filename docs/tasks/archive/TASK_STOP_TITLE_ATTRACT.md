# TASK_STOP_TITLE_ATTRACT — граница конца inference-клипа

**Статус:** done  
**Закрыто:** 2026-07-20 — secondary `go_freeze` (`terminate_reason=game_over_screen`); DoD visual PASS; пост-hoc trim FM2 `logs/20260718`+`20260719` по тому же сигналу.  
**Приоритет:** high  
**Ветка:** `task/stop-title-attract` (`83a8931` → main).  
**Зависит от:** —  
**Файлы:** `src/env/base_nes_env.py`, `games/rushn_attack/env/`, `games/rushn_attack/env_config.yaml`, `src/attempt_logger.py`, `src/achievements/playlist.py`, `src/fm2_export.py`, `fceux/lua/achievement_overlay_playlist.lua`, `docs/GAME_RUSHN_ATTACK.md`, `docs/SCRIPTS.md`, `docs/DESIGN.md`, `games/rushn_attack/missions/m1/reference/go_to_attract{,2,3,_another_place}.fm2`  
**Контекст в чат:** этот файл + [DESIGN.md](../../DESIGN.md) § ядро/плагин + файлы из шпаргалки выше  

**Тупик (не merge):** `experiment/stop-title-attract` (`9eef8af`) — pose-stop `x=129` + trim по `death_x==129`.

### Цель

Inference-клип (FM2 / playlist) должен заканчиваться на **границе попытки агента**: полный осмысленный проход жизней — **без** GAME OVER → title → attract в записи и **без** обрезания живого геймплея.

Триггер: confirmed deaths до бюджета; secondary — конец **до** или **на** границе GO, не после входа в title/attract. Не голый `x=129`, не слепой trim.

### Чеклист сессии

- [x] Probe слоёв raw FM2 / playlist / playback hold
- [x] Эталон + `death_confirm_steps`; hex room
- [x] Observability `terminate_reason` / `death_count`
- [x] Playlist без trim-by-`death_x`
- [x] Unit death_mode + RnA title/attract secondary
- [x] Pluggable Core: title/attract в `RushnAttackEnv` + `env_config.yaml`, не в ядре
- [x] Эталон GO→title→attract: `reference/go_to_attract{,2,3,_another_place}.fm2` + ram_scout + визуал; **`y` не инвариант**; GO с другого места уровня → тот же `r=0,x=129`
- [x] Secondary stop на **GO-freeze** (`r=0,x=129`, `y∉title_ys`, confirm≥32) — код + unit
- [x] **DoD visual:** клип без GO→title→attract (оператор) — **PASS 2026-07-20** (`logs/20260720/ep0001.fm2`, `terminate_reason=game_over_screen`)
- [x] Пост-hoc trim существующих FM2 по GO-freeze: `logs/20260718` (5/12) + `logs/20260719` (25/25) + refresh `playlist.json` airtime

### Критерий готовности (DoD)

- [x] Новый inference-клип: **нет** GAME OVER / title menu / attract demo в просмотре
- [x] Не early-stop на flicker / короткий mid-flash коридора
- [x] Hold между клипами OK (probe п.3)
- [x] Игро-специфика в плагине ([DESIGN](../../DESIGN.md) Pluggable Core / Template Method)
- [x] Unit зелёные; experiment не merge
- [x] Исторические плейлисты 18–19.07 обрезаны по GO-freeze (без title/attract в хвосте)

### Операторский visual FAIL (2026-07-20, вечер)

Клип: `tmp/smoke/visual_one_clip/` — `terminate_reason=title_screen` @ **1447** env-steps (`fm2≈5788` frames), `death_count=0`, end RAM `r=0,x=129,y=133,L=6`.

Просмотр playlist (`play_inference_fm2`, overlay HUD):

| f (HUD) | Что на экране | HUD |
| ------- | ------------- | --- |
| **5031** | **GAME OVER** (белый текст на чёрном) | `r=0x00 L=6` |
| **5714** | **Title** (Konami / Rush'n Attack / 1 PLAYER) | `r=0x00 L=6` |
| **5918** | **Attract demo** (коридор, бег; score у 1P пустой — признак demo) | `r=0x00 L=6` |

`f=5918` > длины movie (~5788) — хвост attract может быть **hold/free-run** после movie; GO@5031 и title@5714 — **внутри** FM2.

**Выводы (зафиксировать):**

1. Цель **не** достигнута: в клипе есть полная цепочка GO → title → (далее attract).
2. Экран **GAME OVER при `L=6`** — secondary по `lives<1` его **не видит**; `death_count` тоже 0 (нет confirmed death).
3. Стоп по attract standing (`y∈{131,133,135}`, confirm=24) срабатывает **слишком поздно**: к моменту terminate уже записаны GO и title.
4. Нужен эталон/сигнал именно **экрана GAME OVER** (или более ранний конец попытки), не только поза title standing / `lives<1`.
5. Эталон закрыт п. **GO-etalon** ниже: GO ≠ title standing; **`y=95` не инвариант** (см. go3 → `y=41`); якорь — **durable freeze**, не `lives`.

Ранее: гейт только `level≥0x08` не включал secondary при gen0 в `room=0` → `min_attempt_steps`; confirm 32→24 убрал «4 цикла» до truncate, но не убрал GO→title из хвоста.

### Эталон GO→title→attract (2026-07-20, вечер)

**Артефакты:** `reference/go_to_attract.fm2` (+ `…2`, `…3`, `…_another_place`) — play → GO → title → attract.  
**Scout:** `ram_scout.py … --no-ram-map` на каждый; канон `clear` scout / `ram_resolve` / `ram_map` **не** трогали; dump — `tmp/smoke/go_to_attract/` (gitignore).  
**Не** `build_playthrough` — слот `human_playthrough.jsonl` один.

#### Сводка FM2 (кросс-проверка позы)

| FM2 | frames | GO window | GO pose | Title после GO | `L` на GO |
| --- | ------ | --------- | ------- | -------------- | --------- |
| `go_to_attract` | 6784 | **2958–3619** (662f) | `r=0 x=129` **`y=95`** freeze | 3642–3753 `y∈{131,133,135}` | **6** |
| `go_to_attract2` | 3583 | **2772–3194** (423f) | `r=0 x=129` **`y=95`** freeze | 3204–3328 | **6** |
| `go_to_attract3` | 5029 | **4136–4803** (668f) | `r=0 x=129` **`y=41`** freeze | 4829–4923 | **6** |
| `go_to_attract_another_place` | 10412 | **9522–10187** (666f) | `r=0 x=129` **`y=41`** freeze | ~10230–10320 | **6** |

**`y=95` отвергнут как единственный якорь:** go3 / another_place — **`y=41`**.  
**«Другое место уровня»:** до GO герой был при **`x≈8`** (не 129); на экране GO RAM всё равно **`x=129`**. Сигнал GO не зависит от места смерти в коридоре `room=0`.

**Общее на всех GO (4 клипа):**

| Признак | Значение |
| ------- | -------- |
| `room` | `0x00` |
| `x` | `129` |
| `lives` | **6** (durable drain нет) |
| Поведение | **freeze** одного `(x,y)` сотни кадров (~7–11 с) |
| Затем | title standing `y∈{131,133,135}`, потом attract |
| `0x00EF` | **64** весь GO-window |
| `0x0001` | **1** почти весь GO (title обычно 0; attract тоже 1) |

**Сигнал GO (кандидат):**

| Критерий | Деталь |
| -------- | ------ |
| Match | `room==0` + `x==129` + `lives≥1` + **`y ∉ {131,133,135}`** + **тот же `(x,y)` держится** |
| Confirm | **≥32** (conf=24 → early false; **32+** — hit только в GO; max non-GO freeze ≤**31f** на another_place, ранее ≤27) |
| Не делать | фиксировать один `go_y`; голый `x=129` без freeze/confirm |

**Жизни:** на GO→title→attract во всех клипах **`L=6`**. Primary death-budget и secondary `lives<1` этот путь не видят.

#### Операторская визуальная разметка `go_to_attract.fm2` (2026-07-20)

Формат: скрин FCEUX + кадр `N/6784` на overlay. Подойдёт как эталон для калибровки.

| f (HUD) | На экране | Согласование с RAM |
| ------- | --------- | ------------------ |
| **31** | Title intro (Konami / 1 PLAYER) | early title, `L=0` (до gameplay) |
| **192** | Intro cinema (горы / ночь) | не end-attract |
| **1096** | Gameplay (лестница, HUD 1P) | обычная игра |
| **2970** | **GAME OVER** (белый текст, чёрный фон) | внутри RAM-freeze **2958–3619** (`y=95`); текст виден ≈**+12f** после старта freeze |
| **3635** | Title после GO (1 PLAYER) | ≈**−7f** до RAM title-pose **3642–3753** |
| **3805** | Attract/demo (лестница снова) | ≈ RAM attract start **~3810** |

**Следствие:** freeze начинается чуть **раньше** видимого GO; title standing чуть **позже** первого кадра меню. Confirm≥32 на freeze всё ещё попадает в видимый GO (стоп ~f=2989 — уже с текстом GO на экране).

#### Операторская визуальная разметка `go_to_attract2.fm2` (2026-07-20, подробно)

| f (HUD) | На экране | Согласование с RAM |
| ------- | --------- | ------------------ |
| **22** | Title intro | early title |
| **216** | Intro cinema (горы) | не end-attract |
| **1042** | Чёрный экран (fade в уровень) | transition, не GO |
| **1087** | Gameplay start, HUD сверху ещё пустой | вход в уровень |
| **1101** | Gameplay + HUD (`1P`, score, `POW=0`) | обычная игра |
| **2721** | **Death**: герой лежит, враги бегут, HUD жив | **до** GO-freeze; не стоп-критерий сам по себе |
| **2780** | **GAME OVER** (белый текст, чёрный фон) | внутри RAM-freeze **2772–3194** (`y=95`); текст ≈**+8f** после старта freeze |
| **3224** | Title после GO (1 PLAYER) | внутри RAM title-pose **3204–3328** |
| **3347** | Чёрный экран (fade title→attract) | transition |
| **3391** | Attract/demo (бег у лестницы, HUD) | после title |

**Уточнения относительно go1:**

1. Цепочка визуально: gameplay → **death pose** → GO → title → black → attract.
2. Death @2721 **не** совпадает с началом freeze (2772): ~50f анимации смерти до GO-экрана.
3. Чёрный экран @1042 / @3347 — **не** GAME OVER (нет текста); нельзя стопить по «весь кадр чёрный».
4. Confirm≥32 от freeze@2772 → стоп ~f=2803 — уже на видимом GO (2780).

#### Операторская визуальная разметка `go_to_attract3.fm2` (2026-07-20)

| f (HUD) | На экране | Согласование с RAM |
| ------- | --------- | ------------------ |
| **4137** | **GAME OVER** | RAM-freeze **4136–4803** (`y=41`); текст ≈**+1f** после старта freeze |
| **4823** | Title после GO (1 PLAYER) | ≈**−6f** до RAM title-pose **4829–4923** |
| **4993** | Attract/demo (лестница) | после title; movie ends @5029 |

**Кросс go1/go2/go3/another_place (визуал ↔ RAM):**

| FM2 | GO text f | Freeze start | Δ | Title f | Attract f |
| --- | --------- | ------------ | - | ------- | --------- |
| go1 | 2970 | 2958 | +12 | 3635 | 3805 |
| go2 | 2780 | 2772 | +8 | 3224 | 3391 |
| go3 | 4137 | 4136 | **+1** | 4823 | 4993 |
| another_place | **9533** | **9522** | +11 | **10213** | **10375** |

Freeze всегда начинается **не позже** видимого GO (Δ 1–12f). Confirm≥32 от start freeze → стоп уже на кадре с текстом GO во всех клипах.

#### Операторская визуальная разметка `go_to_attract_another_place.fm2` (2026-07-20)

| f (HUD) | На экране | Согласование с RAM |
| ------- | --------- | ------------------ |
| **9533** | **GAME OVER** | freeze **9522–10187** (`y=41`); до GO gameplay @ `x≈8` → snap к `x=129` |
| **10213** | Title после GO | переход; title_ys с ~10230 |
| **10375** | Attract/demo (лестница, красная стрелка GO) | после title; movie ends @10412 |

**Вывод another_place:** смерть/обрыв **не у x=129** не ломает детектор — экран GO всё равно даёт `r=0,x=129` + freeze. Отдельный checkpoint (`cp` остался 0) глубже по миссии всё ещё не покрыт, но для коридора `room=0` якорь подтверждён.

**Выводы:**

1. Пробел эталона закрыт **четырьмя** GO-цепочками (+ визуал) в `reference/`.
2. Ориентир — **durable freeze** на `room=0,x=129` вне title_ys (+ опц. `0x00EF==64`), **не** `lives`, **не** фиксированный `y`, **не** title standing.
3. Visual FAIL: terminate на title_ys слишком поздно; GO уже в FM2.
4. Следующий шаг кода (плагин RnA): secondary `go_freeze` confirm≥32 — **сделано** (`terminate_reason=game_over_screen`); DoD visual — оператор.
5. Антискоуп «голый `x=129`» остаётся: нужен freeze+confirm и исключение title_ys.
6. Визуал подтверждает RAM-GO ≈ экран GAME OVER; death pose и чёрный fade — не якоря стопа. GO с другого места в `room=0` — тот же сигнал.

#### Inference smoke go_freeze (2026-07-20, ночь)

Код: `go_freeze_confirm_steps: 32` в `episode_end_title`; `terminate_reason=game_over_screen`.

| | |
|--|--|
| Клип | `tmp/smoke/visual_go_freeze/ep0001.fm2` (+ `logs/20260720/ep0001.fm2`) |
| Прогон | `gen0` stochastic, `inference_cp0`, 1 ep |
| steps | **948** env (`fm2` **3792** frames) |
| `terminate_reason` | **`game_over_screen`** |
| `death_count` | **0** |
| end RAM | `r=0x00 x=129 y=95 L=6` (GO-freeze, не title_ys) |

Play: `./.venv/Scripts/python.exe scripts/play_fm2_gui.py tmp/smoke/visual_go_freeze/ep0001.fm2`  
**DoD visual — PASS (оператор 2026-07-20):** клип без GO→title→attract; обрыв на GO-freeze.

### Не делать (антискоуп)

- Merge `experiment/stop-title-attract` в main
- Стоп записи по позе `room + title_x=129` как главный критерий
- Слепой `trim_fm2_tail_frames` / trim по `death_x==129`
- OBS / Twitch / пересбор часового эфирного плейлиста как цель задачи
- Смена reward / train hyperparams
- Повтор [ISSUE_INFERENCE](ISSUE_INFERENCE.md) (title **в начале** playback / embed) — только ссылка при пересечении

### Исследование (2026-07-20)

Оператор видит title/attract в конце просмотра; путь «стоп на title-позе» и experiment **не согласуются с логами**.

#### Probe raw FM2 tail (2026-07-20) — пункт 1

Инструмент: `probe_movie_playback_ppu` @ `mf ∈ {n−600, n−120, n−1}` на `logs/20260718/ep0001,02,04,05.fm2` (turbo playmovie). Артефакты в `tmp/smoke/` — очищены после прогона.

| Клип | n frames | @ −600 | @ −120 | @ −1 (конец movie) |
| ---- | -------- | ------ | ------ | ------------------ |
| ep0001 | 7116 | gameplay `r=0,x≈5,L=6`, PPU≠title | то же | то же — **без title в хвосте** |
| ep0002 | 6444 | gameplay `L=6` | **`r=0,x=129,L=6`, PPU title_like** | `r=17,x=129,L=5`, PPU чёрный (death flash?) |
| ep0004 | 8260 | gameplay `L=6` | **`r=0,x=129,L=6`, PPU title_like** | `r=9,x=129,L=5`, PPU чёрный |
| ep0005 | 9132 | gameplay `L=6` | **`r=0,x=129,L=6`, PPU title_like** | `r=17,x=129,L=5`, PPU чёрный |

**Вердикт пункта 1:** title/attract-подобный участок **бывает внутри raw FM2** (~2 с до конца: `room=0,x=129,L=6` + PPU title_like) у ep0002/04/05; ep0001 — чистый gameplay до конца. Самый последний кадр — скорее death/black (`L=5`, ненулевой room), не меню «1 PLAYER». Симптом **не сводится** только к playback free-run; слой записи/FM2 тоже участвует. Слепой trim 25 с по `death_x` по-прежнему отвергнут (режет и нормальный геймплей @ −600).

#### Probe playlist FM2 tail (2026-07-20) — пункт 2

Все 25 клипов `logs/20260719/playlist.json`: `fm2_frames == episode_frames×4 − 1500` (trim experiment). Probe short/median/long: `04_many_achievements_{020,021,006}.fm2` @ `mf ∈ {n−600, n−120, n−1}`.

| Клип | n (после trim) | steps×4 | trim | хвост −600/−120/−1 |
| ---- | -------------- | ------- | ---- | ------------------ |
| …_020 (ep21) | 5032 | 6532 | 1500 | везде gameplay `r=0,x≈1–6,L=6`, PPU≠title |
| …_021 (ep22) | 6632 | 8132 | 1500 | то же |
| …_006 (ep7) | 16116 | 17616 | 1500 | то же |

**Вердикт пункта 2:** после trim 1500 хвост playlist FM2 — **чистый gameplay**, без title/attract внутри movie. Trim срезал title-like хвост raw (п.1), но с запасом ~25 с и ценой геймплея. Если оператор всё ещё видит title/attract на эфире/playlist — искать в **playback free-run после movie** (пункт 3), не в байтах этих FM2.

#### Probe playback hold (2026-07-20) — пункт 3

Имитация слоя playlist: `-playmovie` → при конце movie `movie.stop`/`close` → free-run. Сэмплы `@ hold ∈ {0,60,180,600,1800}` (default hold плейлиста = **180**). PPU screenshot в этом прогоне не записался (`title_like=null`) — вердикт по **RAM**.

| Клип | конец FM2 (п.1–2) | hold 0…1800 после stop |
| ---- | ----------------- | ---------------------- |
| `20260719/…_020.fm2` (trimmed) | gameplay `L=6` | стабильно `r=0,x≈4–5,L=6`, `movie_active=false` — **без title/attract за 30 с** |
| `20260718/ep0004.fm2` (raw) | deathish `r=8,x=129,L=5` | hold0: death; **hold60: refill `L=5→6`, `r=0,x=155`** (не классический title `x=129,L=0`); дальше corridor/gameplay `L=6` |

**Вердикт пункта 3:** для **текущего playlist 20260719** (trim + hold≈180) free-run **не** уводит в title/attract в пределах hold и даже ~30 с. Симптом оператора на этом плейлисте **не объясняется** post-movie hold. На raw death-хвосте free-run даёт быстрый lives-refill/смену позы — отдельно от меню title; длинный attract за 30 с не поймали. Главный слой title-like для raw — **внутри FM2** (п.1); trim — костыль (п.2), не канон.

#### Эталон конца попытки (2026-07-20) — пункт 4

**Источники:** `human_playthrough.jsonl` (полного GO нет), dense RAM-probe хвоста `ep0004.fm2` (шаг 30 кадров, последние ~5 с), attempts 18–19.07, G0.

**Отвергнутые одиночные сигналы (ложные друзья)**

| Сигнал | Почему нельзя |
| ------ | ------------- |
| `x == 129` | В эталоне у gameplay (`lives∈[1,9]`) **3935** кадров с `x=129` (в т.ч. коридор `room=0x00`) |
| `room == 0` | И title, и стартовый коридор |
| `lives == 0` один кадр | Анимация смерти; не GO |
| `death_x == 129` → trim | Путает death в level с title; см. п.2 |

**Dense хвост raw ep0004 (n=8260)** — title-like **до** logged death, не «после полного GO»:

| from_end | RAM | Интерпретация |
| -------- | --- | ------------- |
| −300…−180 | `r=0, x=0/155, L=6` | обычный геймплей |
| −150…−30 | `r=0, x=129, L=6` | title-like поза при **ещё валидных** lives (+ PPU title_like @ −120, п.1) |
| −1 | `r=9, x=129, L=5` | событие потери жизни (6→5) |

Attempts: конец с `death_lives=5` — обрыв на **первой** (или ранней) смерти, не на исчерпании бюджета 6.

**Канон для записи (рабочий эталон → п.5)**

1. **Primary:** N-е **подтверждённое** событие потери жизни, N = `lives` на старте эпизода после валидного gameplay-чтения (`lives∈[1,9]`).  
   Confirm: dip `lives` держится ≥ `death_confirm_steps`, и это **строго больше** max flicker на смене комнаты (эмпирика ≤3 env-step → confirm ≥4).  
   Terminate на step подтверждения N-й смерти — **не ждать** title/attract.
2. **Secondary (страховка, не главный путь):** после ≥1 confirmed death — устойчивый `lives<1` + title-room (hex-parse `"0x.."`, не `int("0x00")`) ≥ `confirm_steps`. Attract с `lives≥1` этим не ловится.
3. Сырой `lives` — **только** как вход в confirmed-death / secondary; никогда единственный триггер.

**Пробел эталона (закрыт 2026-07-20 вечером):** полный drain/`lives→0` по-прежнему может отсутствовать; эталон soft-reset GO→title→attract при **`L=6`** — `reference/go_to_attract{,2,3,_another_place}.fm2` (GO-freeze при разном `y`; с другого места уровня — тот же `r=0,x=129`).

**Вердикт пункта 4:** эталон зафиксирован — **бюджет подтверждённых death-событий**, не поза `x=129`. Реализация — п.5; отдельно выяснить, почему текущие inference attempts рвутся при `L=5` (flicker сжигает бюджет vs фактический early stop).

#### Terminate по эталону (2026-07-20) — пункт 5

Сделано в `task/stop-title-attract` (без pose `x=129` / trim):

- `BaseNesEnv`: `death_confirm_steps` (generic); dip lives подтверждается streak'ом; flicker откатывается.
- `_title_screen_match`: room через `_parse_room_id` / `_ram_int` (bridge `"0x00"`).
- `games/rushn_attack/env_config.yaml`: `death_confirm_steps: 4`; `episode_end_title` — secondary only.
- `make_env` прокидывает `death_confirm_steps` из config.
- Unit: flicker / confirm streak / hex room string — `tests/test_death_mode.py`.

#### Observability / playlist / docs (п.6–9)

- `AttemptLogger`: `terminate_reason`, `death_count`; `death_lives` всегда из end-RAM. Tests: `tests/test_attempt_logger.py`.
- Playlist: `trim_fm2_*` / trim-by-`death_x` **нет** в `src/achievements/playlist.py`. Hold≈180 оставлен: probe п.3 — после gameplay-конца не уходит в title/attract за hold и даже ~30 с.
- Антирегрессия: unit death_mode + attempt_logger зелёные (flicker не death).
- SCRIPTS: ложного описания trim на main нет; GAME_RUSHN_ATTACK — `death_confirm_steps` + secondary title.

#### Inference smoke + probe (2026-07-20)

Прогон: `gen0` + `inference_cp0`, `death_mode=game_over`, `death_confirm_steps=4`, FM2 в `tmp/smoke/` (очищен).

| Метрика | Результат |
| ------- | --------- |
| steps | **8000** (= `max_episode_steps`, truncate) |
| `death_count` / `terminate_reason` | **0** / `null` |
| end RAM | `r=0x00, x=129, y=133, L=6` |
| probe −600 / −120 | gameplay, PPU≠title |
| probe −1 | **`r=0,x=129,L=6`, PPU title_like** |

Diag (4000 steps): **16** смен lives, все вида `6→5→6` за 2–3 step (pending≤1, затем откат) — **ни одной confirmed death**. Исторические «смерти» в attempts с `L=5` с высокой вероятностью были **flicker**, сжигавшие budget при `confirm=1`.

**Вердикт smoke:** `death_confirm_steps` работает как задумано (flicker ≠ death). DoD **не закрыт**: без real death эпизод доходит до truncate и пишет title-like кадр. Нужен критерий конца при attract/`L=6` или ином soft-reset **без** возврата к голому `x=129` early-stop (новый пункт чеклиста Gap).

#### Gap fix + live smoke (2026-07-20, позже)

Эталон: flash `r=0,x=129,y∈{131,133,135},L=6` ≤~28 env-step mid-episode; standing title в human — при `L=0`. Не голый `x=129`.

| Механизм | Роль |
| -------- | ---- |
| `pose_confirm_steps: 45` + level-room | secondary terminate на редкий длинный soft-reset `L≥1` |
| `truncate_grace_steps: 40` + `truncate_cool_steps: 16` | не `truncated` mid title-room flash / короткий cool после смены room |
| unit | corridor не стопит; flash < confirm; grace/cool; death-поза level без cool |

Live: arm truncate на входе в flash → `deferred_steps>0`, end RAM `y=137` (не title-pose), `ok_grace`. PPU `title_like` @ `x=129` — шум эвристика, не критерий.

| Источник | Факт |
| -------- | ---- |
| `logs/20260718`, `20260719` attempts | Все `died=true`: `death_room∈{0x0F,0x10}`, `(x,y)=(129,131)`, **`death_lives=5`** |
| Title в эталоне | `room=0x00`, `x=129`, часто `lives=0` (`human_playthrough`, G0) |
| Хвост `inference_inputs` | trailing noop ~1–22 env-step (≪ 15–25 с) |
| Playlist `20260719` | у **всех 25** клипов `episode_frames×4 − fm2_frames == 1500` (trim experiment по `death_x==129`) |
| Smoke experiment | `terminate_reason=title_screen` на **~203** steps — ложный ранний стоп |

**Следствие (дополнено probe п.1):** `death_x=129` в attempts — конец на death/`L=5`, не доказательство «весь хвост = title». У части raw FM2 за ~2 с до конца movie уже есть title-like (`r=0,x=129,L=6` + PPU). Trim на ~25 с всё равно режет и нормальный геймплей (@ −600).

```text
Оператор: title/attract в конце просмотра
    ├─ запись env (когда terminated)
    ├─ содержимое FM2 (последние кадры movie)
    └─ playback (free-run после movie end)
Тупик experiment: pose-stop room+x=129 → early stop
                 trim 900/1500 по death_x=129 → режет gameplay
```

**Уже в main / почему не закрывает**

- `episode_end_title` (`bf579be`): `lives<1` + room + confirm — запасной путь, не канон конца попытки.
- Баг: `_title_screen_match` делает `int(ram["room"])` при bridge `"0x00"` → `ValueError`; `_parse_room_id` есть, в match не используется.
- Критерий не ловит attract с `lives≥1`.
- FM2 на main = все steps до terminate, без trim; в SCRIPTS.md trim описан с experiment (дрейф доков).
- Playlist Lua: после movie finished — hold ~180 кадров свободной эмуляции — отдельный слой симптома.
- Attempts не пишут `terminate_reason` / `death_count`.

**Гипотезы (проверять на п.5+)**

- Сырой RAM `lives` (`0x0017`) шумит: анимация смерти →0; dip `6→5→6` на смене комнаты. Эталон п.4: только confirmed death / secondary.
- При `death_mode=game_over` бюджет может сгорать на flicker → обрыв с `L=5` до настоящего GO; title-like в raw появляется **до** этой смерти (−150…−30), не только «после GO».
- Штатная цепочка после настоящего GO: gameplay → GO-freeze → title → attract; эталон — `reference/go_to_attract{,2,3,_another_place}.fm2` (GO @ `y∈{95,41}`, title @ `y∈{131,133,135}`, всё при `L=6`; another_place: до GO `x≈8`, на GO снова `x=129`).

**Отвергнуто**

- `experiment/stop-title-attract`: pose-return + refill + trim-by-death_x; early stop; игро-эвристики в `BaseNesEnv`.
