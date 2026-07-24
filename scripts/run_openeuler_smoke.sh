#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

DOCKER_CMD="${DOCKER_CMD:-docker}"
IMAGE="${AGENTMEM_OPENEULER_IMAGE_TAG:-agentmem-openeuler:24.03}"
OPENEULER_IMAGE="${OPENEULER_IMAGE:-hub.oepkgs.net/openeuler/openeuler:24.03}"
OUT="${AGENTMEM_OPENEULER_SMOKE_OUT:-results/openeuler-smoke}"
MODEL="${AGENTMEM_MODEL:-Qwen2.5-7B-Instruct}"
BASE_URL="${AGENTMEM_LLM_BASE_URL:-http://47.108.145.21/v1}"
METRICS_URL="${AGENTMEM_VLLM_METRICS_URL:-http://47.108.145.21/metrics}"
CACHE_STATS_URL="${AGENTMEM_CACHE_STATS_URL:-http://47.108.145.21/v1/agentmem/cache_stats}"
REPEAT="${AGENTMEM_SMOKE_REPEAT:-1}"
FORCE_REBUILD="${AGENTMEM_FORCE_REBUILD:-0}"

if ! ${DOCKER_CMD} info >/dev/null 2>&1; then
  if command -v sudo >/dev/null 2>&1 && sudo -n ${DOCKER_CMD} info >/dev/null 2>&1; then
    DOCKER_CMD="sudo ${DOCKER_CMD}"
  else
    echo "Docker daemon is not accessible. Try: sudo dockerd > /tmp/dockerd.log 2>&1 &" >&2
    echo "Or run with: DOCKER_CMD='sudo docker' bash scripts/run_openeuler_smoke.sh" >&2
    exit 2
  fi
fi

if [[ "${FORCE_REBUILD}" == "1" ]] || ! ${DOCKER_CMD} image inspect "${IMAGE}" >/dev/null 2>&1; then
  echo "[1/3] Building ${IMAGE} from ${OPENEULER_IMAGE}"
  ${DOCKER_CMD} build \
    --build-arg "OPENEULER_IMAGE=${OPENEULER_IMAGE}" \
    -f docker/Dockerfile.agent-openeuler \
    -t "${IMAGE}" .
else
  echo "[1/3] Reusing existing image ${IMAGE}"
fi

echo "[2/3] Verifying openEuler userspace and AgentMem CLI"
${DOCKER_CMD} run --rm "${IMAGE}" bash -lc '
set -euo pipefail
cat /etc/os-release
bash scripts/verify_openeuler.sh
python3 -m agentmem --help >/dev/null
echo "AgentMem CLI OK"
'

echo "[3/3] Running real-model smoke benchmark -> ${OUT}"
if [[ -e "${OUT}" ]]; then
  rm -rf "${OUT}" 2>/dev/null || {
    echo "Host cleanup failed; retrying cleanup inside Docker as root"
    ${DOCKER_CMD} run --rm --user 0 \
      -v "${ROOT_DIR}/results:/workspace/agentmem/results" \
      -e "AGENTMEM_CLEAN_OUT=${OUT}" \
      "${IMAGE}" bash -lc 'rm -rf "/workspace/agentmem/${AGENTMEM_CLEAN_OUT}"'
  }
fi
mkdir -p "${OUT}"
chmod 0777 "${OUT}"
${DOCKER_CMD} run --rm \
  -v "${ROOT_DIR}/results:/workspace/agentmem/results" \
  -e "AGENTMEM_LLM_BACKEND=vllm" \
  -e "AGENTMEM_LLM_BASE_URL=${BASE_URL}" \
  -e "AGENTMEM_MODEL=${MODEL}" \
  -e "AGENTMEM_API_KEY=${AGENTMEM_API_KEY:-EMPTY}" \
  -e "AGENTMEM_VLLM_METRICS_URL=${METRICS_URL}" \
  -e "AGENTMEM_CACHE_STATS_URL=${CACHE_STATS_URL}" \
  -e "AGENTMEM_EXTRACTOR_ENABLED=${AGENTMEM_EXTRACTOR_ENABLED:-false}" \
  -e "AGENTMEM_EXTRACTOR_BASE_URL=${AGENTMEM_EXTRACTOR_BASE_URL:-${BASE_URL}}" \
  -e "AGENTMEM_EXTRACTOR_MODEL=${AGENTMEM_EXTRACTOR_MODEL:-${MODEL}}" \
  -e "AGENTMEM_EXTRACTOR_API_KEY=${AGENTMEM_EXTRACTOR_API_KEY:-EMPTY}" \
  -e "AGENTMEM_OUTPUT_DIR=${OUT}" \
  -e "AGENTMEM_SEED=${AGENTMEM_SEED:-20260721}" \
  -e "AGENTMEM_CONTAINER_IMAGE=${OPENEULER_IMAGE}" \
  -e "AGENTMEM_OPENEULER_SMOKE_OUT=${OUT}" \
  -e "AGENTMEM_SMOKE_REPEAT=${REPEAT}" \
  "${IMAGE}" bash -lc '
set -euo pipefail
OUT="${AGENTMEM_OPENEULER_SMOKE_OUT}"
mkdir -p "${OUT}/raw" "${OUT}/logs"

bash scripts/verify_openeuler.sh | tee "${OUT}/logs/openeuler_check.log"
python3 scripts/verify_environment.py --output "${OUT}/environment.json"

python3 -m agentmem benchmark \
  --config configs/config.yaml \
  --scenario tool-heavy \
  --repeat "${AGENTMEM_SMOKE_REPEAT}" \
  --backend vllm \
  --output "${OUT}/raw"

python3 -m agentmem report --results-dir "${OUT}/raw" --config configs/config.yaml >/dev/null
cp "${OUT}/raw/report.md" "${OUT}/report.md"
cp "${OUT}/raw/summary.csv" "${OUT}/summary.csv"

python3 - <<PY
from agentmem.metrics.validation import validate_results_dir, write_validation
result = validate_results_dir("${OUT}/raw")
write_validation("${OUT}/validation.json", result)
print("validation", result.valid)
PY

echo "DONE: ${OUT}"
'

echo
echo "openEuler smoke complete:"
echo "  ${OUT}/environment.json"
echo "  ${OUT}/validation.json"
echo "  ${OUT}/report.md"
