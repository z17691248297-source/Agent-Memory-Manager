from __future__ import annotations

import re
from pathlib import Path

from agentmem.tools.path_policy import PROJECT_ROOT, resolve_allowed_path

ALLOWED_ROOTS = [PROJECT_ROOT / "benchmarks" / "fixtures", PROJECT_ROOT / "examples"]


def read_file(input_text: str, context: dict | None = None) -> str:
    path = _extract_path(input_text)
    if path is None:
        return _mock_large_file()

    target = resolve_allowed_path(path, ALLOWED_ROOTS)
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"文件不存在: {path}")
    return target.read_text(encoding="utf-8", errors="replace")


def _extract_path(text: str) -> str | None:
    match = re.search(r"([\w./-]+\.(txt|md|py|csv|log))", text)
    return match.group(1) if match else None
def _mock_large_file() -> str:
    return "\n".join(
        f"第 {idx} 行：这是一个用于 benchmark 的模拟大文件内容，包含 Agent 记忆管理和工具结果外置说明。"
        for idx in range(1200)
    )
