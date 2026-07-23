# TASK_POLICY_SEPARATION — разделение политик обучения (пилот: title / cutscene)

**Статус:** open  
**Приоритет:** high  
**Ветка:** `task/policy-separation` — проработку этой задачи выполнять **только в этой ветке**.  
**Зависит от:** конец попытки RnA по game-over-freeze ([TASK_STOP_TITLE_ATTRACT](archive/TASK_STOP_TITLE_ATTRACT.md), done); `start` уже в `games/rushn_attack/env_config.yaml` actions (Discrete меняется → нужен retrain).  
**Файлы (ориентиры, уточнить в постановке):** `src/train/train_ppo.py`, `src/stream/run_inference.py`, `src/env/base_nes_env.py`, `games/rushn_attack/env/`, `games/rushn_attack/env_config.yaml`, `docs/DESIGN.md`, `docs/ML_CONCEPT.md`, `docs/GAME_RUSHN_ATTACK.md`, `docs/GLOSSARY.md`  
**Контекст в чат:** этот файл + [DESIGN.md](../DESIGN.md) (Pluggable Core / слоты) + [GAME_RUSHN_ATTACK.md](../GAME_RUSHN_ATTACK.md) § действия / конец эпизода

Каркас: [TASK_BLANK.md](TASK_BLANK.md)

### Цель

Ввести в каркас **разделение политик** (несколько обученных политик / голов с явной маршрутизацией по фазе экрана), чтобы геймплейная политика не искажалась опытом title / intro / cutscene и позже — боссов и иных жанровых режимов.

Первый практический срез — **начало Rush'n Attack**: отдельная политика (или голова) для title / стартовой cutscene (в т.ч. `start`), переключение на геймплейную политику после входа в уровень. Это учебный и продуктовый пилот механизма, а не одноразовый хак под одну игру.

### Почему не «скрипт на фазу»

Скриптовый remap действий на title/attract **не** изолирует искажение [PPO](../GLOSSARY.md#ppo): в буфер rollout всё равно попадает чужой режим, градиенты смешивают несовместимые задачи. Разделение политик — выбранный путь проекта (см. отказ от скриптового `TASK_NON_GAMEPLAY_PHASES`).

### Архитектурные рамки ([DESIGN](../DESIGN.md))

| Слой | Что принадлежит |
| ---- | --------------- |
| **Ядро** | нейтральный механизм: реестр политик, выбор по `phase_id` / сигналу env, train/inference API без `if game_id` |
| **Плагин** | детектор фазы (YAML + hooks в `games/<id>/env/`), список фаз, какие кнопки/награды у фазы |

Не копировать `src/train/` под игру. Новый слот в DESIGN (если ещё нет) — до кода.

### Чеклист сессии

- [ ] Зафиксировать термины в [GLOSSARY](../GLOSSARY.md) (разделение политик / фаза экрана / `phase_id`) и слот в [DESIGN](../DESIGN.md)
- [ ] Постановка v1: контракт сигнала фазы из env (`info` / obs aux), формат артефактов `models/` (одна zip с головами vs несколько файлов), поведение reset/switch
- [ ] Детектор фаз RnA (только плагин): title / intro-cutscene / gameplay; числа и match — в YAML/hooks, не в ядре
- [ ] Ядро: загрузка ≥2 политик + маршрутизация step в train и inference
- [ ] Пилот обучения: политика intro (`start` / выход из title-cutscene) + политика gameplay; датасет/награда intro не смешивать с corridor-PPO без явного решения
- [ ] Inference: тот же switch, что train; клип/attempts отражают смену политики (observability)
- [ ] Smoke / unit на switch и на «геймплейная политика не вызывается на title»
- [ ] Обновить [SCRIPTS](../SCRIPTS.md) / [GAME_RUSHN_ATTACK](../GAME_RUSHN_ATTACK.md) при смене CLI или контракта models
- [ ] Запись уроков пилота → заметки ниже (что переиспользовать для боссов / multi-genre)

### Критерий готовности (DoD)

- [ ] Есть документированный **ядерный** механизм ≥2 политик с переключением по фазе (без игро-констант в `src/`)
- [ ] Пилот RnA: с cold/title-like старта агент стабильно доходит до геймплея отдельной intro-политикой; дальше играет gameplay-политикой
- [ ] Геймплейный PPO **не** обучается на шагах title/cutscene пилота (изоляция опыта подтверждена логом / метрикой)
- [ ] Unit/smoke зелёные; Pluggable Core соблюдён
- [ ] Антискоуп не нарушен; глоссарий и DESIGN обновлены

### Не делать (антискоуп)

- Скриптовый remap / «behavior on phase» как продуктовый путь вместо политик
- Возврат title/attract **confirm-stop** как замена разделению политик (конец попытки RnA — game-over-freeze, уже в main)
- Игро-специфика title/cutscene RnA в `src/env/base_nes_env.py` / `src/train/`
- Полный multi-genre / все боссы в этом TASK (только задел API + один пилот intro)
- Ломать Discrete совместимость без явной пометки retrain / нового `genN`

### Заметки / гипотезы

- **Контекст решения (2026-07-23):** после GO-only exit и добавления `start` отвергнут скриптовый контур non-gameplay phases; нужен именно multi-policy / multi-head.
- Старт с `save_states/cp0.fc0` (уже в геймплее) **не** заменяет пилот: нужен сценарий с реальным title/cutscene (отдельный reset state или cold path), иначе intro-политика не тренируется.
- Кандидаты реализации (выбрать в постановке, не заранее): multi-head Shared backbone; отдельные `PPO` zip + router; options/hierarchical later — вне v1, если раздувает объём.
- Будущие фазы (босс, меню паузы, смена жанра) должны стыковаться к тому же `phase_id` API без нового TASK-каркаса.
- Старые модели Discrete(9) без `start` несовместимы с текущим action space — пилот = новое поколение / явная миграция.
