#!/usr/bin/env bash
set -euo pipefail
python - <<'PY'
from agentmem_vllm.request_parser import parse_agent_meta
meta=parse_agent_meta({'agent_meta': {'agent_id':'a','session_id':'s','segment_type':'shared_prefix','priority':'high','ttl_seconds':60}})
assert meta and meta.segment_type == 'shared_prefix'
print('agentmem_vllm skeleton ok')
PY
