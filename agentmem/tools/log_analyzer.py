from __future__ import annotations

import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TOOL_HEAVY_DATASET = PROJECT_ROOT / "benchmarks" / "fixtures" / "tool_heavy_scaled.log"


def analyze_logs(input_text: str, context: dict | None = None) -> str:
    """Return the configured benchmark log, falling back to the original generator."""

    dataset = _dataset_path(input_text, context)
    if dataset and dataset.exists() and dataset.is_file():
        return dataset.read_text(encoding="utf-8")
    if DEFAULT_TOOL_HEAVY_DATASET.exists():
        return DEFAULT_TOOL_HEAVY_DATASET.read_text(encoding="utf-8")
    return generate_original_tool_heavy_log()


def generate_original_tool_heavy_log(line_count: int = 3000) -> str:
    """生成可复现的原始大日志，用于派生 tool-heavy benchmark 数据。"""
    lines: list[str] = []
    for idx in range(line_count):
        if idx == 180:
            msg = "ERROR CUDA OOM while allocating KV cache block"
        elif idx == 777:
            msg = "WARN timeout waiting for decode batch"
        elif idx == 1500:
            msg = "ERROR KV cache allocation failed: no free blocks"
        elif idx == 2310:
            msg = "exception in worker: simulated RuntimeError"
        else:
            msg = f"INFO request={idx % 31} prefill_tokens={128 + idx % 512} decode_step={idx % 64}"
        lines.append(f"2026-06-20T12:{idx % 60:02d}:00Z {msg}")
    return "\n".join(lines)


def _dataset_path(input_text: str, context: dict | None) -> Path | None:
    context = context or {}
    value = context.get("optional_log_path") or context.get("dataset") or _path_from_input(input_text)
    if not value:
        return None
    path = Path(str(value))
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _path_from_input(input_text: str) -> str:
    for line in str(input_text or "").splitlines():
        match = re.match(r"\s*(?:dataset|optional_log_path|log_path)\s*:\s*(\S+)\s*$", line, re.IGNORECASE)
        if match:
            return match.group(1)
    return ""
