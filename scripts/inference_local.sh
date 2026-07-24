#!/usr/bin/env bash
# Inference + FM2 + playlist: preflight cleanup → run_inference → опц. эфир.
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

PLAY=false
SKIP_PREFLIGHT=false
WIPE_GEN_LOGS=false
ARGS=()
for arg in "$@"; do
  case "$arg" in
    --play) PLAY=true ;;
    --skip-preflight) SKIP_PREFLIGHT=true ;;
    --wipe-gen-logs) WIPE_GEN_LOGS=true ;;
    *) ARGS+=("$arg") ;;
  esac
done

GAME="rushn_attack"
MISSION="m1"
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

if [[ ${#ARGS[@]} -eq 0 ]]; then
  ARGS=(
    --episodes 5
    --max-steps 1200
    --stochastic
    --save-episode-fm2
    --build-playlist
  )
fi
# --model default: gen0.zip (run_inference)

if [[ "$SKIP_PREFLIGHT" == false ]]; then
  echo "inference: preflight (keep gen logs by default; staging/bridge) ..."
  PRE_ARGS=(--game "$GAME" --mission "$MISSION")
  if [[ -n "$MODEL" ]]; then
    PRE_ARGS+=(--model "$MODEL")
  fi
  if [[ -n "$MODEL_VERSION" ]]; then
    PRE_ARGS+=(--model-version "$MODEL_VERSION")
  fi
  if [[ "$WIPE_GEN_LOGS" == true ]]; then
    PRE_ARGS+=(--wipe-gen-logs)
  fi
  # Согласовано с run_inference default --model gen0.zip
  if [[ -z "$MODEL" && -z "$MODEL_VERSION" ]]; then
    PRE_ARGS+=(--model gen0.zip)
  fi
  "$PY" scripts/inference_preflight.py "${PRE_ARGS[@]}"
fi

"$PY" src/stream/run_inference.py --skip-preflight --game "$GAME" --mission "$MISSION" "${ARGS[@]}"

if [[ "$PLAY" == true ]]; then
  RESOLVE_MODEL="${MODEL:-gen0.zip}"
  GEN_DIR="$("$PY" -c "
import sys
sys.path.insert(0, 'src')
from jsonl_logs import resolve_default_model_version
from project_paths import mission_dir
print(resolve_default_model_version(
    mission_dir(sys.argv[1], sys.argv[2]),
    model=sys.argv[3] or None,
    model_version=sys.argv[4] or None,
))
" "$GAME" "$MISSION" "$RESOLVE_MODEL" "$MODEL_VERSION")"
  MANIFEST="games/${GAME}/missions/${MISSION}/logs/${GEN_DIR}/playlist.json"
  if [[ ! -f "$MANIFEST" ]]; then
    echo "inference: playlist not found: $MANIFEST" >&2
    exit 1
  fi
  echo "inference: playback $MANIFEST"
  "$PY" scripts/inference_preflight.py --playback-only
  "$PY" scripts/play_inference_fm2.py "$MANIFEST" --game "$GAME" --mission "$MISSION" --skip-preflight
fi
