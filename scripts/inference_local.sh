#!/usr/bin/env bash
# Inference: два сценария.
#   Pool  — --playlist-cnt N → logs/genN/ + плейлист (ачивки)
#   Live  — --live: окно FCEUX до Ctrl+C, без записи пула
# Дефолты game/mission — config/workspace.yaml (резолв в Python).
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

SKIP_PREFLIGHT=false
WIPE_GEN_LOGS=false
LIVE=false
ARGS=()
for arg in "$@"; do
  case "$arg" in
    --skip-preflight) SKIP_PREFLIGHT=true ;;
    --wipe-gen-logs) WIPE_GEN_LOGS=true ;;
    --live) LIVE=true; ARGS+=("$arg") ;;
    *) ARGS+=("$arg") ;;
  esac
done

GAME=""
MISSION=""
MODEL=""
MODEL_VERSION=""
idx=0
while [[ $idx -lt ${#ARGS[@]} ]]; do
  case "${ARGS[$idx]}" in
    --game)
      GAME="${ARGS[$((idx + 1))]}"
      idx=$((idx + 2))
      ;;
    --mission)
      MISSION="${ARGS[$((idx + 1))]}"
      idx=$((idx + 2))
      ;;
    --model)
      MODEL="${ARGS[$((idx + 1))]}"
      idx=$((idx + 2))
      ;;
    --model-version)
      MODEL_VERSION="${ARGS[$((idx + 1))]}"
      idx=$((idx + 2))
      ;;
    *)
      idx=$((idx + 1))
      ;;
  esac
done

if [[ "$LIVE" == true ]]; then
  if [[ "$WIPE_GEN_LOGS" == true ]]; then
    echo "inference: error: --live нельзя с --wipe-gen-logs (live не пишет пул)" >&2
    exit 1
  fi
  for a in "${ARGS[@]+"${ARGS[@]}"}"; do
    if [[ "$a" == "--playlist-cnt" ]]; then
      echo "inference: error: --live нельзя с --playlist-cnt (это pool)" >&2
      exit 1
    fi
  done
  has_stochastic=false
  for a in "${ARGS[@]+"${ARGS[@]}"}"; do
    if [[ "$a" == "--stochastic" ]]; then
      has_stochastic=true
      break
    fi
  done
  if [[ "$has_stochastic" == false ]]; then
    ARGS+=(--stochastic)
  fi
else
  # Pool: пустой argv → короткий прогон с плейлистом
  if [[ ${#ARGS[@]} -eq 0 ]]; then
    ARGS=(
      --playlist-cnt 5
      --max-steps 1200
      --stochastic
    )
  fi
fi

if [[ "$SKIP_PREFLIGHT" == true && "$WIPE_GEN_LOGS" == true ]]; then
  echo "inference: error: --wipe-gen-logs нельзя с --skip-preflight (wipe выполняется в preflight)" >&2
  exit 1
fi

if [[ "$SKIP_PREFLIGHT" == false ]]; then
  if [[ "$LIVE" == true ]]; then
    echo "inference: preflight (live — пул не трогаем) ..."
  else
    echo "inference: preflight (pool; keep gen logs by default) ..."
  fi
  PRE_ARGS=()
  if [[ -n "$GAME" ]]; then
    PRE_ARGS+=(--game "$GAME")
  fi
  if [[ -n "$MISSION" ]]; then
    PRE_ARGS+=(--mission "$MISSION")
  fi
  if [[ -n "$MODEL" ]]; then
    PRE_ARGS+=(--model "$MODEL")
  fi
  if [[ -n "$MODEL_VERSION" ]]; then
    PRE_ARGS+=(--model-version "$MODEL_VERSION")
  fi
  if [[ "$WIPE_GEN_LOGS" == true ]]; then
    PRE_ARGS+=(--wipe-gen-logs)
  fi
  if [[ -z "$MODEL" && -z "$MODEL_VERSION" ]]; then
    PRE_ARGS+=(--model gen0.zip)
  fi
  "$PY" scripts/inference_preflight.py "${PRE_ARGS[@]}"
fi

"$PY" src/stream/run_inference.py --skip-preflight "${ARGS[@]}"
