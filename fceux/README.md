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

Прямая ссылка (GitHub release):

```
https://github.com/TASEmulators/fceux/releases/download/v2.6.6/fceux-2.6.6-win64.zip
```

Для side-by-side тестов (N2 / другой portable без замены рабочего): распаковать в `fceux/portable_<label>/` и задать `FCEUX_HOME` (см. ниже). Примеры: `portable_github_v266/` (2.6.6), `portable_222_win32/` (2.2.2, `fceux.exe`).

## Режимы (один binary, разные профили)

| Профиль | Lua | Turbo | Окно | Назначение |
| ------- | --- | ----- | ---- | ---------- |
| `record` | `lua/record_logger.lua` | выкл | да | Запись эталона, FM2 |
| `train` | `lua/bridge.lua` | вкл | скрыто | PPO, N parallel env |
| `inference` | `lua/bridge.lua` | выкл | да | Эфир, OBS capture |

Launcher (`src/env/`) читает `runtime.yaml` + `profiles/<mode>.yaml`.

## Согласованность

- [Save state](docs/ML_CONCEPT.md) привязан к **версии FCEUX** и **хэшу ROM** — версию фиксировать в `playthrough_manifest.yaml` (`fceux_version: "2.6.6"`).
- Обновление FCEUX → пересоздать save states на CP-границах.
- Qt/SDL-порт **не использовать** в этом проекте (несовместим с save states classic-порта).

## Переопределение пути

`FCEUX_HOME` — каталог portable (если не `fceux/portable/`). Реализовано в `src/project_paths.resolve_fceux_home()`; влияет на `fceux64.exe` и `fcs/`.

```bash
FCEUX_HOME=fceux/portable_github_v266 ./.venv/Scripts/python.exe scripts/play_inference_fm2.py ...
```
