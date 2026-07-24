#!/usr/bin/env bash
set -euo pipefail
echo "No patch is bundled for an unknown vLLM version. Provide a target-version patch in vllm_integration/patches/." >&2
exit 2
