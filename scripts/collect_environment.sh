#!/usr/bin/env bash
set -euo pipefail
OUTPUT="${1:-results/environment.json}"
python -m scripts.verify_environment --output "${OUTPUT}"
