#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "${PYTHON_BIN}" ]]; then
  if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
    PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  else
    PYTHON_BIN="$(command -v python)"
  fi
fi

bash scripts/clean_results.sh

"${PYTHON_BIN}" -m agentmem benchmark --scenario tool-heavy --output results
"${PYTHON_BIN}" -m agentmem benchmark --scenario long-session --output results
"${PYTHON_BIN}" -m agentmem benchmark --scenario multi-stage --output results
"${PYTHON_BIN}" -m agentmem benchmark --scenario branching --output results
"${PYTHON_BIN}" -m agentmem benchmark --scenario prefix-cache --output results
"${PYTHON_BIN}" -m agentmem benchmark --scenario ablation --output results
"${PYTHON_BIN}" -m agentmem report --results-dir results

echo "All benchmark results are under: ${ROOT_DIR}/results"
echo "Main report: ${ROOT_DIR}/results/report.md"
