#!/usr/bin/env bash
set -euo pipefail
python - <<'PY'
import importlib.util, json
spec=importlib.util.find_spec('vllm')
print(json.dumps({'installed': bool(spec), 'path': spec.origin if spec else None}, indent=2))
PY
