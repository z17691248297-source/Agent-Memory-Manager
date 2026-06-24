from __future__ import annotations

from dataclasses import dataclass

from agentmem.tools.spec import ToolSpec


@dataclass
class RouteDecision:
    selected_tool_names: list[str]
    route_reason: dict[str, str]


class ToolRouter:
    """规则版工具路由器，默认不依赖 LLM。"""

    RULES: dict[str, list[str]] = {
        "log_analyzer": ["日志", "log", "error", "oom", "timeout", "kv cache", "failed"],
        "file_reader": ["文件", "file", "读取", "content"],
        "calculator": ["计算", "calculate", "加", "减", "乘", "除", "+", "-", "*", "/"],
        "code_analyzer": ["代码", "class", "function", "def", "bug", "todo", "fixme"],
        "csv_analyzer": ["csv", "表格", "统计", "平均值", "列"],
        "repo_scanner": ["仓库", "目录", "repo", "项目结构"],
    }

    def route(
        self,
        user_input: str,
        stage: str,
        available_tools: list[ToolSpec],
        top_k: int = 2,
    ) -> RouteDecision:
        # Tool execution is deliberately confined to the tool_calling stage so
        # planning/reflection benchmark steps do not accidentally inflate prompt
        # tokens just because their text mentions logs or code.
        if stage != "tool_calling":
            return RouteDecision(selected_tool_names=[], route_reason={})

        text = user_input.lower()
        available = {tool.name: tool for tool in available_tools if tool.enabled}
        matched: list[tuple[ToolSpec, str]] = []

        for tool_name, keywords in self.RULES.items():
            if tool_name not in available:
                continue
            for keyword in keywords:
                if keyword.lower() in text:
                    matched.append((available[tool_name], f"命中关键词: {keyword}"))
                    break

        matched.sort(key=lambda pair: (-pair[0].priority, pair[0].name))
        selected = matched[:top_k]
        return RouteDecision(
            selected_tool_names=[tool.name for tool, _ in selected],
            route_reason={tool.name: reason for tool, reason in selected},
        )
