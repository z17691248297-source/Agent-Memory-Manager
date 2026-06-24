from __future__ import annotations

from pathlib import Path


IGNORE = {".git", ".venv", "venv", "__pycache__", ".pytest_cache"}


def scan_repo(input_text: str, context: dict | None = None) -> str:
    root = Path(".").resolve()
    entries: list[str] = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(part in IGNORE for part in rel.parts):
            continue
        if "results" in rel.parts and "raw" in rel.parts:
            continue
        if len(entries) >= 500:
            entries.append("[目录条目已截断]")
            break
        prefix = "dir " if path.is_dir() else "file"
        entries.append(f"{prefix} {rel}")
    key_files = [line for line in entries if any(name in line for name in ["README", "pyproject", "agentmem", "benchmark", "script"])]
    return "\n".join(["仓库扫描结果:", "关键文件:", *key_files[:80], "目录树:", *entries[:300]])

