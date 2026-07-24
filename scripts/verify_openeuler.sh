#!/usr/bin/env bash
set -euo pipefail
if [[ -r /etc/os-release ]] && grep -qi openeuler /etc/os-release; then
  echo "openEuler userspace detected"
else
  echo "openEuler userspace not detected"
fi
