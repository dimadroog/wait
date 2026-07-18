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
ARGS=()
for arg in "$@"; do
  case "$arg" in
    --play) PLAY=true ;;
    --skip-preflight) SKIP_PREFLIGHT=true ;;
    *) ARGS+=("$arg") ;;
  esac
done

GAME="rushn_attack"
MISSION="m1"
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
  echo "inference: preflight cleanup (logs, play_fm2 staging, bridge IPC) ..."
  "$PY" scripts/inference_preflight.py --game "$GAME" --mission "$MISSION"
fi

"$PY" src/stream/run_inference.py --skip-preflight --game "$GAME" --mission "$MISSION" "${ARGS[@]}"

if [[ "$PLAY" == true ]]; then
  DATE_PREFIX="$(date -u +%Y%m%d)"
  MANIFEST="games/${GAME}/missions/${MISSION}/logs/${DATE_PREFIX}/playlist.json"
  if [[ ! -f "$MANIFEST" ]]; then
    echo "inference: playlist not found: $MANIFEST" >&2
    exit 1
  fi
  echo "inference: playback $MANIFEST"
  "$PY" scripts/inference_preflight.py --playback-only
  "$PY" scripts/play_inference_fm2.py "$MANIFEST" --game "$GAME" --mission "$MISSION" --skip-preflight
fi
