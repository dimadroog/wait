# TASK_STOP_TITLE_ATTRACT — граница конца inference-клипа

**Статус:** open  
**Приоритет:** high  
**Ветка:** `task/stop-title-attract` — проработку этой задачи выполнять **только в этой ветке**.  
**Зависит от:** —  
**Файлы:** `src/env/base_nes_env.py`, `games/rushn_attack/env/`, `games/rushn_attack/env_config.yaml`, `src/attempt_logger.py`, `src/achievements/playlist.py`, `src/fm2_export.py`, `fceux/lua/achievement_overlay_playlist.lua`, `docs/GAME_RUSHN_ATTACK.md`, `docs/SCRIPTS.md`, `docs/DESIGN.md`  
**Контекст в чат:** этот файл + [DESIGN.md](../DESIGN.md) § ядро/плагин + файлы из шпаргалки выше  

**Тупик (не merge):** `experiment/stop-title-attract` (`9eef8af`) — pose-stop `x=129` + trim по `death_x==129`.

### Цель

Inference-клип (FM2 / playlist) должен заканчиваться на **границе попытки агента**: полный осмысленный проход жизней — **без** долгого idle title/attract после game over / soft-reset и **без** обрезания живого геймплея.

Триггер: confirmed deaths до бюджета; secondary — title/attract idle после попытки (`RushnAttackEnv`). Не голый `x=129`, не слепой trim.

### Чеклист сессии

- [x] Probe слоёв raw FM2 / playlist / playback hold
- [x] Эталон + `death_confirm_steps`; hex room
- [x] Observability `terminate_reason` / `death_count`
- [x] Playlist без trim-by-`death_x`
- [x] Unit death_mode + RnA title/attract secondary
- [x] Pluggable Core: title/attract в `RushnAttackEnv` + `env_config.yaml`, не в ядре
- [ ] **DoD visual:** клип без долгого idle title/attract после конца попытки (оператор)

### Критерий готовности (DoD)

- [ ] Новый inference-клип: нет длительного idle title/attract после GO/soft-reset
- [x] Не early-stop на flicker / mid-flash (`confirm` > flash)
- [x] Hold между клипами OK (probe)
- [x] Игро-специфика в плагине ([DESIGN](../DESIGN.md) Pluggable Core / Template Method)
- [x] Unit зелёные; experiment не merge

**2026-07-20 visual:** в клипе `death_count=0`, весь прогон `room=0x00` — гейт secondary только по `level≥0x08` **никогда не включался**; оператор видел несколько title/attract (PPU) при `L=6`, не «после GO». Фикс: `min_attempt_steps` OR level OR death.

### Не делать (антискоуп)

- Merge `experiment/stop-title-attract` в main
- Стоп записи по позе `room + title_x=129` как главный критерий
- Слепой `trim_fm2_tail_frames` / trim по `death_x==129`
- OBS / Twitch / пересбор часового эфирного плейлиста как цель задачи
- Смена reward / train hyperparams
- Повтор [ISSUE_INFERENCE](archive/ISSUE_INFERENCE.md) (title **в начале** playback / embed) — только ссылка при пересечении

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

**Пробел эталона:** в `human_playthrough` нет полного drain жизней → GO→title; калибровка secondary — по controlled smoke (п.8) / будущему GO-прогону.

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
- Штатная цепочка после настоящего GO: gameplay → title → attract; сейчас в логах полного GO нет.

**Отвергнуто**

- `experiment/stop-title-attract`: pose-return + refill + trim-by-death_x; early stop; игро-эвристики в `BaseNesEnv`.
