#!/usr/bin/env bash
# Запуск PPO по tasks/train_task.json или с CLI-аргументами.
# Дефолты train (BACKLOG 1.1–1.8): fceux/profiles/train.yaml + train_ppo --n-envs 6 (H2 RAM на 16 GB).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -x "./.venv/Scripts/python.exe" ]]; then
  PY="./.venv/Scripts/python.exe"
elif [[ -x "./.venv/bin/python" ]]; then
  PY="./.venv/bin/python"
else
  echo "venv not found — run scripts/setup_venv.ps1" >&2
  exit 1
fi

echo "train: preflight cleanup (train_/bench_ IPC + orphan FCEUX/python) ..."
"$PY" scripts/train_preflight.py

TASK="${1:-}"
if [[ -n "$TASK" && "$TASK" == *.json ]]; then
  exec "$PY" src/train/train_ppo.py --task "$TASK" "${@:2}"
fi

exec "$PY" src/train/train_ppo.py --n-envs 6 "$@"
