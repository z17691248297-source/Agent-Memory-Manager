from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentmem.experiment import get_git_commit, utc_timestamp


def _read(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return "unavailable"


def _cmd(command: list[str]) -> str:
    try:
        return subprocess.check_output(command, text=True, stderr=subprocess.DEVNULL, timeout=10).strip()
    except Exception:
        return "unavailable"


def _pip_hash() -> str:
    freeze = _cmd([sys.executable, "-m", "pip", "freeze"])
    return hashlib.sha256(freeze.encode()).hexdigest() if freeze != "unavailable" else "unavailable"


def collect_environment() -> dict:
    os_release = _read("/etc/os-release")
    is_container = Path("/.dockerenv").exists() or "docker" in _read("/proc/1/cgroup") or "containerd" in _read("/proc/1/cgroup")
    is_openeuler = "openeuler" in os_release.lower()
    return {
        "timestamp": utc_timestamp(),
        "os_release": os_release,
        "kernel": platform.release(),
        "architecture": platform.machine(),
        "cpu": platform.processor() or _cmd(["uname", "-p"]),
        "memory": _read("/proc/meminfo").splitlines()[:5],
        "python_version": platform.python_version(),
        "pip_freeze_hash": _pip_hash(),
        "git_commit": get_git_commit(),
        "container_runtime": "container" if is_container else "native_or_unknown",
        "container_image": os.getenv("AGENTMEM_CONTAINER_IMAGE", "unavailable"),
        "model_endpoint": os.getenv("AGENTMEM_LLM_BASE_URL", "unavailable"),
        "metrics_endpoint": os.getenv("AGENTMEM_VLLM_METRICS_URL", "unavailable"),
        "vllm_version": os.getenv("AGENTMEM_VLLM_VERSION", "unavailable"),
        "model_name": os.getenv("AGENTMEM_MODEL", "unavailable"),
        "openEuler_userspace_container_verified": bool(is_openeuler and is_container),
        "openEuler_native_host_verified": bool(is_openeuler and not is_container),
        "Ubuntu_model_server_verified": False,
        "full_openEuler_gpu_deployment_verified": False,
        "official_os_compatibility_run": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = collect_environment()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
