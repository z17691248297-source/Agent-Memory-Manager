#!/usr/bin/env bash
set -euo pipefail

RED=$'\033[31m'
RESET=$'\033[0m'
DEMO_START_TS=$(date +%s)

section() {
  printf '\n%s========== %s ==========%s\n' "$RED" "$1" "$RESET"
}

pause_for_video() {
  sleep "${DEMO_PAUSE_SECONDS:-2}"
}

section "1. 连接自部署模型"
python - <<'PY'
import json
import os
import urllib.request

RED = "\033[31m"
RESET = "\033[0m"

def key(name: str) -> str:
    return f"{RED}{name}{RESET}"

base_url = os.environ.get("AGENTMEM_LLM_BASE_URL")
if not base_url:
    raise SystemExit("ERROR: AGENTMEM_LLM_BASE_URL is required")

with urllib.request.urlopen(base_url.rstrip("/") + "/models", timeout=20) as response:
    payload = json.loads(response.read().decode("utf-8"))

items = payload.get("data", [])
if not items:
    raise SystemExit("ERROR: /v1/models returned no models")

for item in items:
    print(f"{key('model id')}: {item.get('id', '')}")
    max_model_len = (
        item.get("max_model_len")
        or item.get("max_model_length")
        or item.get("max_context_len")
        or "服务未返回（可选字段）"
    )
    print(f"{key('max_model_len')}: {max_model_len}")
PY
pause_for_video

section "2. 多轮对话和记忆"
python demo/demo_chat_memory.py
pause_for_video

section "3. agent_meta / MemoryPlan"
if find results_demo_chat/memory_plan -type f -print -quit >/tmp/agentmem_demo_plan_path 2>/dev/null && [ -s /tmp/agentmem_demo_plan_path ]; then
  python - <<'PY'
import json
from collections import Counter
from pathlib import Path

RED = "\033[31m"
RESET = "\033[0m"

def key(name: str) -> str:
    return f"{RED}{name}{RESET}"

path = Path(Path("/tmp/agentmem_demo_plan_path").read_text(encoding="utf-8").strip())
rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
segments = Counter(str(row.get("segment_type", "")) for row in rows)
priorities = Counter(str(row.get("priority", "")) for row in rows)
agent_meta_sent = any(bool(row.get("agent_meta")) for row in rows)

print(f"{key('MemoryPlan 文件路径')}: {path}")
print(f"{key('记录条数')}: {len(rows)}")
print(f"{key('segment_type 分布')}: {dict(segments)}")
print(f"{key('priority 分布')}: {dict(priorities)}")
print(f"{key('agent_meta_sent')}: {agent_meta_sent}")
print("说明: MemoryPlan 记录每轮请求的 cache 语义；现场聊天不强调 token 节省。")
PY
else
  printf '%s\n' "${RED}MemoryPlan 未找到，跳过现场 MemoryPlan 摘要。${RESET}"
fi

if [ -d results_cache_pressure_on_final ]; then
  python scripts/audit_agent_meta.py --results results_cache_pressure_on_final | sed -n '1,30p'
fi
pause_for_video

section "4. 核心 benchmark 摘要"
if [ -f results/final-release-sanitized/exp_20260724T041247Z_ece79c19/summary.csv ]; then
  python demo/demo_summarize_results.py --input results/final-release-sanitized/exp_20260724T041247Z_ece79c19/summary.csv
elif [ -f results/final/final_summary.csv ]; then
  python demo/demo_summarize_results.py --input results/final/final_summary.csv
else
  python demo/demo_summarize_results.py --input final_summary.csv
fi
pause_for_video

DEMO_END_TS=$(date +%s)
printf '\n%sDemo completed in %ss%s\n' "$RED" "$((DEMO_END_TS - DEMO_START_TS))" "$RESET"
