from __future__ import annotations

import re
from pathlib import Path


PROJECT_ROOT = Path.cwd().resolve()


def analyze_code(input_text: str, context: dict | None = None) -> str:
    path = _extract_python_path(input_text)
    if path and Path(path).exists():
        target = Path(path).resolve()
        if not _is_relative_to(target, PROJECT_ROOT):
            raise PermissionError("code_analyzer 只允许分析当前项目目录内的 Python 文件")
        text = target.read_text(encoding="utf-8", errors="replace")
    else:
        text = _mock_code()
    classes = re.findall(r"^\s*class\s+(\w+)", text, re.MULTILINE)
    funcs = re.findall(r"^\s*def\s+(\w+)", text, re.MULTILINE)
    imports = re.findall(r"^\s*(?:import|from)\s+(.+)", text, re.MULTILINE)
    todos = re.findall(r".*(?:TODO|FIXME).*", text, re.IGNORECASE)
    long_funcs = [name for name in funcs if len(name) > 24]
    return "\n".join(
        [
            "代码分析结果:",
            f"class 数量: {len(classes)} -> {classes[:10]}",
            f"function 数量: {len(funcs)} -> {funcs[:20]}",
            f"import 数量: {len(imports)}",
            f"TODO/FIXME: {len(todos)}",
            f"疑似命名过长函数: {long_funcs[:10]}",
            "原始片段:",
            text[:6000],
        ]
    )


def _extract_python_path(text: str) -> str | None:
    match = re.search(r"([\w./-]+\.py)", text)
    return match.group(1) if match else None


def _mock_code() -> str:
    return "\n".join(
        [
            "import os",
            "from pathlib import Path",
            "",
            "class AgentRuntime:",
            "    def run(self):",
            "        pass  # TODO: add timeout",
            "",
            "def very_long_function_name_that_should_be_reviewed():",
            "    # FIXME: split this function",
            "    return True",
        ]
        * 80
    )


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
