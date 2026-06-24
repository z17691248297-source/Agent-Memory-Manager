from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ToolSpec:
    """工具元数据。brief 默认进 prompt，full skill 按需加载。"""

    name: str
    category: str
    brief_description: str
    full_description: str | None
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    skill_path: str
    permission_level: str
    timeout_seconds: int = 5
    max_output_chars: int = 20_000
    cacheable: bool = True
    enabled: bool = True
    tags: list[str] = field(default_factory=list)
    priority: int = 50

    @classmethod
    def from_dict(cls, data: dict[str, Any], skill_path: Path) -> "ToolSpec":
        return cls(
            name=str(data["name"]),
            category=str(data.get("category", "general")),
            brief_description=str(data.get("brief_description", "")),
            full_description=data.get("full_description"),
            input_schema=dict(data.get("input_schema", {})),
            output_schema=dict(data.get("output_schema", {})),
            skill_path=str(skill_path),
            permission_level=str(data.get("permission_level", "read_only")),
            timeout_seconds=int(data.get("timeout_seconds", 5)),
            max_output_chars=int(data.get("max_output_chars", 20_000)),
            cacheable=bool(data.get("cacheable", True)),
            enabled=bool(data.get("enabled", True)),
            tags=list(data.get("tags", [])),
            priority=int(data.get("priority", 50)),
        )

