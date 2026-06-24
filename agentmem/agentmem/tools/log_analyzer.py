from __future__ import annotations


def analyze_logs(input_text: str, context: dict | None = None) -> str:
    """生成可复现的大日志，用于测试工具结果外置。"""
    lines: list[str] = []
    for idx in range(3000):
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

