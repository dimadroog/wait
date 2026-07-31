# rushn_attack — m1 — RAM map

> Сборка эталона: `ram_scout.py` → авто-resolve → **D3 ручная сверка** (clear.fm2, 8492 кадра).

| Адрес | Поле | Тип | Примечание |
| ----- | ---- | --- | ---------- |
| `0x000C` | `room` | u8 | auto; D3: 0x00 на 8416/8492 кадров геймплея, согласовано с env_config level_room_min |
| `0x01EE` | `x` | u8 | manual: D3 title pose x=129 @ f29–45; auto 0x01ED отклонён |
| `0x020D` | `y` | u8 | manual: D3 title pose y∈{131,135} @ 0x020D; auto 0x01EC отклонён |
| `0x0017` | `lives` | u8 | auto; D3: смены 6↔0↔5 на смертях |
| `0x01FB` | `checkpoint` | u8 | auto; D3: оставлен с прошлой проверенной карты |
| `0x0030` | `stage` | u8 | manual: D3 stage 0→9 (кадры 1939…6219) |

## D3 сверка с env_config

| Проверка | Ожидание (`env_config.yaml`) | Результат на clear.fm2 |
| -------- | ------------------------------ | ---------------------- |
| Title pose | `x=129`, `ys=[131,133,135]`, `room=0x00` | f29–45: `0x01EE=129`, `0x020D∈{131,135}`, `0x000C=0x00` |
| Gameplay room | `level_room_min=0x08`, коридор m1 `0x00` | `0x000C=0x00` доминирует на уровне |
| Stage progress | CP по `min_stage` 1…9 | `0x0030`: 0→1 @1939 … 8→9 @6219 |
| Auto x/y | candidates `0x00EC` (scroll/sub) | **не** player x; канон `0x01EE`/`0x020D` |
| `0x0461` (не в карте) | auto-resolve назвал `hp` | init-каскад f1017–1026 на чёрном экране; в Rush'n Attack HP нет |

## Candidates (auto)

> Источник: `reference/scout/ram_scout_candidates.json` · resolve: `config/ram_resolve.json`

| Адрес | Смен | hint |
| ----- | ---- | ---- |
| `0x00EC` | 8465 | maybe_x_increase |
| `0x0002` | 8457 |  |
| `0x0041` | 8457 |  |
| `0x00F6` | 8200 |  |
| `0x0088` | 7976 |  |
| `0x0078` | 7974 |  |
| `0x0098` | 7973 |  |
| `0x0083` | 7423 |  |
| `0x0093` | 7411 |  |
| `0x00B2` | 5474 |  |
| `0x000D` | 4345 |  |
| `0x0701` | 4339 |  |
| `0x0700` | 4338 |  |
| `0x0513` | 4016 | maybe_x_increase |
| `0x00AB` | 3891 |  |
