from __future__ import annotations

from pathlib import Path

from agentmem.tools.calculator import calculate
from agentmem.tools.code_analyzer import analyze_code
from agentmem.tools.csv_analyzer import analyze_csv
from agentmem.tools.file_reader import read_file
from agentmem.tools.log_analyzer import analyze_logs
from agentmem.tools.registry import ToolRegistry
from agentmem.tools.repo_scanner import scan_repo


def build_default_registry(skills_dir: str | Path = "skills") -> ToolRegistry:
    registry = ToolRegistry(skills_dir)
    registry.load_from_skills()
    registry.register_handler("log_analyzer", analyze_logs)
    registry.register_handler("file_reader", read_file)
    registry.register_handler("calculator", calculate)
    registry.register_handler("code_analyzer", analyze_code)
    registry.register_handler("csv_analyzer", analyze_csv)
    registry.register_handler("repo_scanner", scan_repo)
    return registry

