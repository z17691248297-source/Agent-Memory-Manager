from __future__ import annotations

import shutil
import subprocess


def get_peak_gpu_memory_mb() -> int:
    """读取当前 NVIDIA GPU 显存占用；无 GPU 时返回 -1。"""
    if shutil.which("nvidia-smi") is None:
        return -1
    try:
        output = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=memory.used",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=3,
        )
        values = [int(line.strip()) for line in output.splitlines() if line.strip()]
        return max(values) if values else -1
    except Exception:
        return -1

