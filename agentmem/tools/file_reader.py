from __future__ import annotations

import re
from pathlib import Path


ALLOWED_ROOTS = [Path("benchmarks/fixtures").resolve(), Path("examples").resolve()]


def read_file(input_text: str, context: dict | None = None) -> str:
    path = _extract_path(input_text)
    if path is None:
        return _mock_large_file()

    target = Path(path).resolve()
    if not any(_is_relative_to(target, root) for root in ALLOWED_ROOTS):
        raise PermissionError("file_reader 只允许读取 benchmarks/fixtures 或 examples 下的文件")
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"文件不存在: {path}")
    return target.read_text(encoding="utf-8", errors="replace")


def _extract_path(text: str) -> str | None:
    match = re.search(r"([\w./-]+\.(txt|md|py|csv|log))", text)
    return match.group(1) if match else None


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _mock_large_file() -> str:
    return "\n".join(
        f"第 {idx} 行：这是一个用于 benchmark 的模拟大文件内容，包含 Agent 记忆管理和工具结果外置说明。"
        for idx in range(1200)
    )

