#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

CONFIG="configs/config.yaml"
OUTPUT_BASE="results"
SCENARIOS=""
REPEAT=""
WARMUP=""
SEED=""
MODELS="default"
ORDER=""
CACHE_ISOLATION=""
SMOKE=0
RELEASE=0
SKIP_MODEL_CHECK=0
MAX_CONCURRENCY=""
FAKE_PID=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config) CONFIG="$2"; shift 2 ;;
    --output-dir) OUTPUT_BASE="$2"; shift 2 ;;
    --scenarios) SCENARIOS="$2"; shift 2 ;;
    --repeat) REPEAT="$2"; shift 2 ;;
    --warmup) WARMUP="$2"; shift 2 ;;
    --seed) SEED="$2"; shift 2 ;;
    --models) MODELS="$2"; shift 2 ;;
    --order) ORDER="$2"; shift 2 ;;
    --cache-isolation) CACHE_ISOLATION="$2"; shift 2 ;;
    --max-concurrency) MAX_CONCURRENCY="$2"; shift 2 ;;
    --smoke) SMOKE=1; CONFIG="configs/config.smoke.yaml"; shift ;;
    --release) RELEASE=1; CONFIG="configs/config.release.yaml"; shift ;;
    --skip-model-check) SKIP_MODEL_CHECK=1; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [[ ${SMOKE} -eq 1 && ${RELEASE} -eq 1 ]]; then
  echo "--smoke and --release are mutually exclusive" >&2
  exit 2
fi

if [[ -z "${SEED}" ]]; then
  SEED="${AGENTMEM_SEED:-20260721}"
fi
if [[ -z "${REPEAT}" ]]; then
  if [[ ${SMOKE} -eq 1 ]]; then REPEAT=1; elif [[ ${RELEASE} -eq 1 ]]; then REPEAT=5; fi
fi
if [[ -z "${SCENARIOS}" ]]; then
  if [[ ${SMOKE} -eq 1 ]]; then SCENARIOS="tool-heavy"; else SCENARIOS="tool-heavy,long-session,multi-stage,branching,prefix-cache,ablation"; fi
fi
if [[ -z "${ORDER}" ]]; then
  if [[ ${RELEASE} -eq 1 ]]; then ORDER="counterbalanced"; else ORDER="randomized"; fi
fi
if [[ -z "${CACHE_ISOLATION}" ]]; then
  CACHE_ISOLATION="snapshot_delta"
fi

EXPERIMENT_ID="exp_$(date -u +%Y%m%dT%H%M%SZ)_$(python - <<'PY'
import uuid
print(uuid.uuid4().hex[:8])
PY
)"
OUTPUT_DIR="${OUTPUT_BASE%/}/${EXPERIMENT_ID}"
mkdir -p "${OUTPUT_DIR}" "${OUTPUT_DIR}/raw" "${OUTPUT_DIR}/logs" "${OUTPUT_DIR}/events" "${OUTPUT_DIR}/tool_store" "${OUTPUT_DIR}/snapshots"

cleanup() {
  if [[ -n "${FAKE_PID}" ]]; then
    kill "${FAKE_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

export AGENTMEM_EXPERIMENT_ID="${EXPERIMENT_ID}"
export AGENTMEM_SEED="${SEED}"
export AGENTMEM_CACHE_ISOLATION_STRATEGY="${CACHE_ISOLATION}"

if [[ ${SMOKE} -eq 1 ]]; then
  PORT="${AGENTMEM_FAKE_SERVER_PORT:-18080}"
  python tests/utils/fake_openai_server.py --port "${PORT}" >"${OUTPUT_DIR}/logs/fake_server.log" 2>&1 &
  FAKE_PID="$!"
  sleep 0.5
  export AGENTMEM_LLM_BACKEND="openai_compatible"
  export AGENTMEM_LLM_BASE_URL="http://127.0.0.1:${PORT}/v1"
  export AGENTMEM_MODEL="fake-agentmem-model"
  export AGENTMEM_API_KEY="fake"
  export AGENTMEM_VLLM_METRICS_URL="http://127.0.0.1:${PORT}/metrics"
  export AGENTMEM_CACHE_STATS_URL="http://127.0.0.1:${PORT}/v1/agentmem/cache_stats"
fi

if [[ ${RELEASE} -eq 1 ]]; then
  BACKEND_CHECK="${AGENTMEM_LLM_BACKEND:-}"
  if [[ "${BACKEND_CHECK}" =~ ^(mock|fake|local|local_deterministic)$ ]]; then
    echo "release mode refuses mock/local backend: ${BACKEND_CHECK}" >&2
    exit 3
  fi
  if [[ -n "${REPEAT}" && ${REPEAT} -lt 5 ]]; then
    echo "release repeat must be >= 5" >&2
    exit 3
  fi
fi

if [[ ${SKIP_MODEL_CHECK} -eq 0 ]]; then
  python - <<'PY'
import os, sys, urllib.request
base=os.environ.get('AGENTMEM_LLM_BASE_URL','').rstrip('/')
if not base:
    print('AGENTMEM_LLM_BASE_URL is required unless --skip-model-check is used', file=sys.stderr)
    sys.exit(4)
try:
    with urllib.request.urlopen(base + '/models', timeout=5) as r:
        if r.status >= 500:
            raise RuntimeError(f'status={r.status}')
except Exception as exc:
    print(f'model endpoint check failed: {exc}', file=sys.stderr)
    sys.exit(4)
PY
fi

python scripts/verify_environment.py --output "${OUTPUT_DIR}/environment.json" >/dev/null
python - <<PY
from pathlib import Path
from agentmem.config import load_config, write_resolved_config, resolved_config_hash
from agentmem.experiment import manifest_base, write_manifest
config=load_config('${CONFIG}', validate=False)
write_resolved_config('${OUTPUT_DIR}/config.resolved.yaml', config)
manifest=manifest_base(
    experiment_id='${EXPERIMENT_ID}',
    config=config,
    config_hash=resolved_config_hash(config),
    output_dir=Path('${OUTPUT_DIR}'),
    seed=int('${SEED}'),
    models='${MODELS}'.split(','),
    scenarios='${SCENARIOS}'.split(','),
    repeat=int('${REPEAT:-1}'),
)
manifest['order']='${ORDER}'
manifest['cache_isolation']='${CACHE_ISOLATION}'
manifest['smoke']=bool(${SMOKE})
manifest['release']=bool(${RELEASE})
if bool(${SMOKE}):
    manifest['real_model']=False
write_manifest('${OUTPUT_DIR}/manifest.json', manifest)
PY

IFS=',' read -r -a MODEL_LIST <<< "${MODELS}"
IFS=',' read -r -a SCENARIO_LIST <<< "${SCENARIOS}"
MULTI_MODEL=0
if [[ ${#MODEL_LIST[@]} -gt 1 ]]; then
  MULTI_MODEL=1
fi
for model_name in "${MODEL_LIST[@]}"; do
  [[ "${model_name}" == "default" ]] || export AGENTMEM_MODEL="${model_name}"
  model_safe="$(echo "${model_name}" | tr -c 'A-Za-z0-9_' '_')"
  model_output="${OUTPUT_DIR}/raw"
  if [[ ${MULTI_MODEL} -eq 1 ]]; then
    model_output="${OUTPUT_DIR}/raw/${model_safe}"
  fi
  for scenario in "${SCENARIO_LIST[@]}"; do
    scenario="$(echo "${scenario}" | xargs)"
    [[ -z "${scenario}" ]] && continue
    BENCHMARK_ARGS=(python -m agentmem benchmark --config "${CONFIG}" --scenario "${scenario}" --repeat "${REPEAT:-1}" --output "${model_output}")
    if [[ -n "${AGENTMEM_LLM_BACKEND:-}" ]]; then
      BENCHMARK_ARGS+=(--backend "${AGENTMEM_LLM_BACKEND}")
    fi
    if [[ -n "${MAX_CONCURRENCY}" ]]; then
      BENCHMARK_ARGS+=(--max-concurrency "${MAX_CONCURRENCY}")
    fi
    "${BENCHMARK_ARGS[@]}"
  done
  if [[ ${MULTI_MODEL} -eq 1 ]]; then
    for csv in "${model_output}"/*.csv; do
      [[ -e "${csv}" ]] || continue
      base="$(basename "${csv}")"
      cp "${csv}" "${OUTPUT_DIR}/raw/${model_safe}_${base}"
    done
  fi
done

python -m agentmem report --results-dir "${OUTPUT_DIR}/raw" --config "${CONFIG}" >/dev/null
cp "${OUTPUT_DIR}/raw/summary.csv" "${OUTPUT_DIR}/summary.csv"
cp "${OUTPUT_DIR}/raw/report.md" "${OUTPUT_DIR}/report.md"
python - <<PY
from agentmem.metrics.validation import validate_results_dir, write_validation
from agentmem.experiment import write_manifest, utc_timestamp
import json
result=validate_results_dir('${OUTPUT_DIR}/raw')
write_validation('${OUTPUT_DIR}/validation.json', result)
manifest=json.loads(open('${OUTPUT_DIR}/manifest.json', encoding='utf-8').read())
manifest['end_time']=utc_timestamp()
manifest['validation_passed']=result.valid
manifest['real_gpu_metrics']=False
write_manifest('${OUTPUT_DIR}/manifest.json', manifest)
PY

echo "experiment_id: ${EXPERIMENT_ID}"
echo "output_dir: ${OUTPUT_DIR}"
echo "report: ${OUTPUT_DIR}/report.md"
