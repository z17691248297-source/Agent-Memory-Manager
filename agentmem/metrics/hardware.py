from __future__ import annotations

import platform
import shutil
import subprocess
from pathlib import Path
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


def collect_os_environment() -> dict[str, Any]:
    os_release = _read_os_release()
    client_os = os_release.get("PRETTY_NAME") or platform.platform()
    environment = _client_environment(os_release)
    official = environment == "openEuler container"
    data: dict[str, Any] = {
        "client_os": client_os,
        "client_environment": environment,
        "official_os_compatibility_run": official,
    }
    if environment == "WSL2":
        data["note"] = "development run only"
    return data


def _read_os_release() -> dict[str, str]:
    path = "/etc/os-release"
    data: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as file:
            for line in file:
                if "=" not in line:
                    continue
                key, value = line.rstrip().split("=", 1)
                data[key] = value.strip().strip('"')
    except OSError:
        return data
    return data


def _client_environment(os_release: dict[str, str]) -> str:
    os_id = os_release.get("ID", "").lower()
    pretty = os_release.get("PRETTY_NAME", "").lower()
    if "openeuler" in os_id or "openeuler" in pretty:
        return "openEuler container" if _running_in_container() else "openEuler"
    if _is_wsl2():
        return "WSL2"
    if "ubuntu" in os_id or "ubuntu" in pretty:
        return "Ubuntu"
    return "unknown"


def _running_in_container() -> bool:
    try:
        with open("/proc/1/cgroup", encoding="utf-8") as file:
            content = file.read()
    except OSError:
        content = ""
    return "docker" in content or "containerd" in content or Path("/.dockerenv").exists()


def _is_wsl2() -> bool:
    try:
        with open("/proc/version", encoding="utf-8") as file:
            version = file.read().lower()
    except OSError:
        return False
    return "microsoft" in version or "wsl2" in version

