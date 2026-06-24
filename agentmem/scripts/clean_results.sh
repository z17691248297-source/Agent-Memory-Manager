#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESULTS_DIR="${ROOT_DIR}/results"
mkdir -p "${RESULTS_DIR}"

find "${RESULTS_DIR}" -type f \( \
  -name "*.csv" -o \
  -name "*.json" -o \
  \( -name "*.md" ! -name "audit_report.md" \) -o \
  -path "*/tool_store/raw/*.txt" -o \
  -path "*/tool_store/chunks/*.txt" \
\) -delete
rm -rf "${RESULTS_DIR}/tool_store"

mkdir -p "${RESULTS_DIR}/tool_store/raw" "${RESULTS_DIR}/tool_store/index" "${RESULTS_DIR}/tool_store/chunks"
echo "results cleaned: ${RESULTS_DIR}"
