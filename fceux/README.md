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
├── operator/          # полный fceux.cfg для Live/GUI (--live / play)
├── runtime.yaml       # версия и путь к binary
└── README.md
```

**Не смешивать** `portable/` (дистрибутив FCEUX) и `lua/` (код проекта) — при обновлении эмулятора перезаписывается только `portable/`. Пресет показа — [`operator/`](operator/README.md): при `--live` целиком копируется в `portable/fceux.cfg`.

## Установка portable

Распакуйте [FCEUX 2.6.6 win64 Binary](https://fceux.com/web/download.html) в `fceux/portable/` (если каталог пуст после clone).

Прямая ссылка (GitHub release):

```
https://github.com/TASEmulators/fceux/releases/download/v2.6.6/fceux-2.6.6-win64.zip
```

Для side-by-side тестов другой сборки: распаковать в произвольный каталог и задать `FCEUX_HOME` (см. ниже). Артефакты N2 — в `tmp/bench/fceux-n2/`.

## Режимы (один binary, разные профили)

| Профиль | Lua | Turbo | Окно | Назначение |
| ------- | --- | ----- | ---- | ---------- |
| `record` | `lua/record_logger.lua` | выкл | да | Запись эталона, FM2 |
| `train` | `lua/bridge.lua` | вкл | headless | PPO, N parallel env |
| `inference` | `lua/bridge.lua` | pool: вкл; Live: выкл | headless; Live: `--live` + `operator/fceux.cfg` | пул логов / операторский live |

Launcher (`src/env/`) читает `runtime.yaml` + `profiles/<mode>.yaml`.

## Lua 5.1 (обязательно)

Встроенный Lua у FCEUX win32/portable — **Lua 5.1**, не 5.2/5.3/5.4 и не LuaJIT с расширениями 5.2+. Писать и править `fceux/lua/*.lua` только с этим контрактом. Полный справочник паттернов 5.1: [www.lua.org/manual/5.1/manual.html#5.4.1](https://www.lua.org/manual/5.1/manual.html#5.4.1).

| Ловушка | Почему ломает | Как правильно |
| ------- | ------------- | ------------- |
| Паттерн `(true\|false)` / любая «альтернатива» через `\|` | В patterns Lua 5.1 **нет** оператора `\|`; `\|` — обычный символ. Матч всегда пустой → флаги вроде `show_window` молча становятся `false` | Читать слово: `text:match('"show_window"%s*:%s*(%a+)') == "true"` (см. `bridge.lua`) |
| `return (a, b, c)` в скобках | Скобки дают **одно** выражение; запятая внутри — syntax error (`')' expected near ','`) | `return a, b, c` без внешних скобок |
| Синтаксис 5.2+ (`goto`, `\x`, bitops как в 5.3) | Скрипт не загрузится или упадёт в runtime | Только диалект 5.1 + API FCEUX (`emu.*`, `gui.*`, `savestate.*`) |
| Молчаливый fail разбора JSON-конфига | Bool/`nil` превращаются в «выкл» без ошибки в Output Console | После смены ключей конфига сверять Python `config.json` и значения в Lua (или явный `error(...)`) |

Типичный симптом ошибки с `\|` в bool: Live `--live`, в JSON `"show_window": true`, на [PPU](../docs/GLOSSARY.md#ppu) серый кадр (`setrenderplanes` остаются выключенными). Сначала проверить парсинг в Lua, не флаги запуска FCEUX.

## Согласованность

- [Save state](docs/ML_CONCEPT.md) привязан к **версии FCEUX** и **хэшу ROM** — версию фиксировать в `playthrough_manifest.yaml` (`fceux_version: "2.6.6"`).
- Обновление FCEUX → пересоздать save states на CP-границах.
- Qt/SDL-порт **не использовать** в этом проекте (несовместим с save states classic-порта).

## Переопределение пути

`FCEUX_HOME` — каталог portable (если не `fceux/portable/`). Реализовано в `src/project_paths.resolve_fceux_home()`; влияет на `fceux64.exe` и `fcs/`.

```bash
FCEUX_HOME=/path/to/other/fceux ./.venv/Scripts/python.exe scripts/play_inference_fm2.py ...
```
