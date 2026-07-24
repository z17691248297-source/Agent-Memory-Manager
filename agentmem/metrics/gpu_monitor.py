from __future__ import annotations

import shutil
import subprocess


def get_peak_gpu_memory_mb(*, same_host_gpu: bool = False) -> int | None:
    """Read local NVIDIA GPU memory only when explicitly configured.

    AgentMem often runs on an openEuler client while vLLM runs on a remote GPU
    host. Local nvidia-smi is therefore not a valid model-server memory metric
    unless same_host_gpu=true is configured by the caller.
    """
    if not same_host_gpu:
        return None
    if shutil.which("nvidia-smi") is None:
        return None
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
        return max(values) if values else None
    except Exception:
        return None
