#!/usr/bin/env bash
set -euo pipefail

MODEL="${MODEL:-${1:-Qwen/Qwen2.5-7B-Instruct}}"
PORT="${PORT:-${2:-8000}}"

echo "Starting vLLM OpenAI-compatible server"
echo "MODEL=${MODEL}"
echo "PORT=${PORT}"

exec vllm serve "${MODEL}" \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --enable-prefix-caching
