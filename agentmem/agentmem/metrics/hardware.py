from __future__ import annotations

import platform
import shutil
import subprocess
from typing import Any


def collect_hardware_info() -> dict[str, Any]:
    """Collect reproducible environment fields for benchmark reports."""
    info: dict[str, Any] = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "gpu": "unavailable",
        "gpu_memory_mb": "unavailable",
        "driver": "unavailable",
    }
    if not shutil.which("nvidia-smi"):
        return info

    command = [
        "nvidia-smi",
        "--query-gpu=name,memory.total,driver_version",
        "--format=csv,noheader,nounits",
    ]
    try:
        output = subprocess.check_output(command, text=True, timeout=3).strip()
    except (OSError, subprocess.SubprocessError):
        return info
    first_gpu = output.splitlines()[0].split(",") if output else []
    if len(first_gpu) >= 3:
        info["gpu"] = first_gpu[0].strip()
        info["gpu_memory_mb"] = first_gpu[1].strip()
        info["driver"] = first_gpu[2].strip()
    return info
