# TASK_STOP_TITLE_ATTRACT — не писать title/attract в inference FM2

**Статус:** open  
**Приоритет:** high  
**Ветка:** `task/stop-title-attract` — проработку этой задачи выполнять **только в этой ветке**.  
**Зависит от:** —  
**Файлы:** `src/env/base_nes_env.py`, `games/rushn_attack/env/`, `games/rushn_attack/env_config.yaml`, `src/achievements/playlist.py`, `src/fm2_export.py`, `fceux/lua/achievement_overlay_playlist.lua`, `docs/DESIGN.md`, `docs/GAME_RUSHN_ATTACK.md`  
**Контекст в чат:** этот файл + [DESIGN.md](../DESIGN.md) § ядро/плагин + файлы из шпаргалки выше  

**Черновик решения (не merge-ready):** ветка `experiment/stop-title-attract` (`9eef8af`).

### Цель

После game over в inference FM2 не должны попадать title screen и attract demo. Эпизод должен заканчиваться на реальном конце попытки (исчерпание жизней / game over), без обрыва геймплея на ранних жизнях и без длинного хвоста меню/демо.

### Архитектурное ограничение (DESIGN)

По [DESIGN.md](../DESIGN.md): **игро-специфика → `games/<game_id>/`**, общее → `src/`.  
Код в `experiment/stop-title-attract` **может противоречить DESIGN**: эвристики Rush'n Attack (`title_x=129`, level-room `≥0x08`, confirm lives dip и т.п.) зашиты в `BaseNesEnv`. Всё, что относится к конкретной игре, должно жить в плагине игры (`games/rushn_attack/…`) через hooks / config / override — и на этапе проработки считается **гипотезой**, не каноном ядра.

### Симптом / наблюдения оператора

- В клипах после game over идут title и attract.
- Черновик в `experiment/stop-title-attract`: клип обрывается **ещё до окончания второй жизни** (стоп слишком агрессивный — ложный `title_screen` / поза `room=0x00,x=129`).

### Чеклист сессии

- [ ] Зафиксировать эталонный критерий конца попытки (RAM/room/x/lives или иной сигнал) на Rush'n Attack без ложных срабатываний в стартовом коридоре
- [ ] Вынести игро-специфику из `BaseNesEnv` в `games/rushn_attack/` (config + hooks); в ядре — только общий механизм
- [ ] Не ломать `death_mode=game_over` для train (ложные dip lives на смене комнаты)
- [ ] Короткий inference-клип в `tmp/smoke/`: полный проход жизней, обрыв без title/attract
- [ ] Согласовать с playlist: post-movie hold / tail-trim — только если нужны после фикса записи
- [ ] Доки: GAME_RUSHN_ATTACK / SCRIPTS; не закреплять гипотезу как API ядра

### Критерий готовности (DoD)

- [ ] Inference FM2 не содержит title/attract после game over
- [ ] Эпизод не обрывается до исчерпания бюджета жизней (нет раннего stop на 1–2-й жизни)
- [ ] Игро-специфика не раздувает `src/env/base_nes_env.py` (соответствие DESIGN)
- [ ] Unit/smoke на смерть + конец эпизода зелёные

### Не делать (антискоуп)

- Пересбор часового эфирного плейлиста
- OBS / Twitch
- Смена reward / train hyperparams
- Merge `experiment/stop-title-attract` в main «как есть»

### Заметки / гипотезы

- Lives RAM (`0x0017`) мигает 6→5→6 на смене комнаты (streak ≤3) — не надёжный счётчик смертей без confirm.
- Поза title/attract: `room=0x00`, `x=129` (G0 / ISSUE_INFERENCE); та же поза бывает в стартовом коридоре → нужен gate (например level-room), иначе ранний stop.
- Bridge отдаёт `room` как `"0x00"` (строка) — парсинг hex обязателен.
- В experiment: playlist `trim_fm2_tail_frames` для `died` клипов; Lua playlist без post-movie hold — отдельный слой (playback), не замена стопа записи.
- Черновик: `experiment/stop-title-attract` — отвалидировать или выкинуть после правильного решения в task-ветке.
