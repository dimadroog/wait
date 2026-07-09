# FCEUX — portable runtime

Официальный **FCEUX 2.6.6 win64 Binary** (classic Win32-порт) живёт в репозитории как portable-сборка.

| Параметр | Значение |
| -------- | -------- |
| Версия | **2.6.6** |
| Порт | **win32** (win64 Binary) — не Qt/SDL |
| Бинарник | `fceux/portable/fceux64.exe` |
| Контракт | `fceux/runtime.yaml` |
| Скачать | [fceux.com/web/download.html](https://fceux.com/web/download.html) |

## Структура

```
fceux/
├── portable/          # официальный zip целиком (exe, dll, palettes, …)
├── lua/               # скрипты проекта (bridge, record_logger)
├── profiles/          # режимы: record | train | inference
├── runtime.yaml       # версия и путь к binary
└── README.md
```

**Не смешивать** `portable/` (дистрибутив FCEUX) и `lua/` (код проекта) — при обновлении эмулятора перезаписывается только `portable/`.

## Установка portable

Распакуйте [FCEUX 2.6.6 win64 Binary](https://fceux.com/web/download.html) в `fceux/portable/` (если каталог пуст после clone).

## Режимы (один binary, разные профили)

| Профиль | Lua | Turbo | Окно | Назначение |
| ------- | --- | ----- | ---- | ---------- |
| `record` | `lua/record_logger.lua` | выкл | да | Запись эталона, FM2 |
| `train` | `lua/bridge.lua` | вкл | скрыто | PPO, N parallel env |
| `inference` | `lua/bridge.lua` | выкл | да | Эфир, OBS capture |

Launcher (`src/env/`, Phase 1) читает `runtime.yaml` + `profiles/<mode>.yaml`.

## Согласованность

- [Save state](docs/ML_CONCEPT.md) привязан к **версии FCEUX** и **хэшу ROM** — версию фиксировать в `playthrough_manifest.yaml` (`fceux_version: "2.6.6"`).
- Обновление FCEUX → пересоздать save states на CP-границах.
- Qt/SDL-порт **не использовать** в этом проекте (несовместим с save states classic-порта).

## Переопределение пути

`FCEUX_HOME` — каталог portable (если не `fceux/portable/`).
