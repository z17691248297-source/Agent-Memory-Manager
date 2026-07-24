#!/usr/bin/env bash
set -euo pipefail
if [[ $# -eq 0 ]]; then
  exec python -m agentmem --help
fi
exec "$@"
