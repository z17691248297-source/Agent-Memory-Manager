from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from agentmem.tools.spec import ToolSpec


ToolCallable = Callable[[str, dict | None], str]


class ToolRegistry:
    """工具注册中心，负责元数据加载、brief 列表和按需 skill 加载。"""

    def __init__(self, skills_dir: str | Path = "skills") -> None:
        self.skills_dir = Path(skills_dir)
        self._specs: dict[str, ToolSpec] = {}
        self._handlers: dict[str, ToolCallable] = {}
        self._skill_cache: dict[str, str] = {}

    def load_from_skills(self) -> None:
        if not self.skills_dir.exists():
            return
        for tool_dir in sorted(self.skills_dir.iterdir()):
            if not tool_dir.is_dir():
                continue
            yaml_path = tool_dir / "tool.yaml"
            skill_path = tool_dir / "SKILL.md"
            if not yaml_path.exists():
                continue
            data = _load_simple_yaml(yaml_path)
            spec = ToolSpec.from_dict(data, skill_path)
            self._specs[spec.name] = spec

    def register(self, tool_spec: ToolSpec, handler: ToolCallable) -> None:
        self._specs[tool_spec.name] = tool_spec
        self._handlers[tool_spec.name] = handler

    def register_handler(self, name: str, handler: ToolCallable) -> None:
        if name not in self._specs:
            raise KeyError(f"工具元数据未加载: {name}")
        self._handlers[name] = handler

    def get_tool(self, name: str) -> ToolSpec:
        if name not in self._specs:
            raise KeyError(f"工具不存在: {name}")
        return self._specs[name]

    def get_handler(self, name: str) -> ToolCallable:
        if name not in self._handlers:
            raise KeyError(f"工具 handler 未注册: {name}")
        return self._handlers[name]

    def list_tool_briefs(self) -> list[dict[str, str]]:
        return [
            {"name": spec.name, "description": spec.brief_description}
            for spec in sorted(self._specs.values(), key=lambda item: (-item.priority, item.name))
            if spec.enabled
        ]

    def load_full_skill(self, name: str) -> str:
        spec = self.get_tool(name)
        if name in self._skill_cache:
            return self._skill_cache[name]
        path = Path(spec.skill_path)
        if not path.exists():
            text = spec.full_description or spec.brief_description
        else:
            text = path.read_text(encoding="utf-8")
        self._skill_cache[name] = text
        return text

    def available_tools(self) -> list[ToolSpec]:
        return [spec for spec in self._specs.values() if spec.enabled]

    def query(self, category: str | None = None, tag: str | None = None) -> list[ToolSpec]:
        specs = self.available_tools()
        if category is not None:
            specs = [spec for spec in specs if spec.category == category]
        if tag is not None:
            specs = [spec for spec in specs if tag in spec.tags]
        return specs


def _load_simple_yaml(path: Path) -> dict:
    """读取本项目受控的简单 YAML；避免为 MVP 引入 PyYAML 依赖。"""
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        return dict(yaml.safe_load(text))
    except Exception:
        # fallback：tool.yaml 同时保持 JSON 兼容写法。
        return dict(json.loads(text))

