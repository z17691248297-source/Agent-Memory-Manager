#!/usr/bin/env bash
set -euo pipefail

MODEL="${MODEL:-${1:-}}"
PORT="${PORT:-${2:-}}"

if [[ -z "${MODEL}" ]]; then
  echo "MODEL or first argument is required, e.g. MODEL=<served-model-name-or-path> $0" >&2
  exit 2
fi
if [[ -z "${PORT}" ]]; then
  echo "PORT or second argument is required, e.g. PORT=<model-port> $0" >&2
  exit 2
fi

echo "Starting vLLM OpenAI-compatible server"
echo "MODEL=${MODEL}"
echo "PORT=${PORT}"

exec vllm serve "${MODEL}" \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --enable-prefix-caching
