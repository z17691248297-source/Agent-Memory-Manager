from __future__ import annotations

from agentmem.memory.memory_object import estimate_tokens
from agentmem.tools.registry import ToolRegistry
from agentmem.tools.result import ToolResult


class BaselineMemory:
    """对照组：完整工具说明、完整历史、完整工具结果全部进入 prompt。"""

    mode = "baseline"

    def __init__(self, system_prompt: str, tool_registry: ToolRegistry) -> None:
        self.system_prompt = system_prompt
        self.tool_registry = tool_registry
        self.messages: list[dict] = []
        self.tool_results: list[ToolResult] = []
        self.last_token_breakdown: dict[str, int] = {}
        self.loaded_skill_names: list[str] = []
        self.loaded_skill_tokens = 0

    def add_user_message(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})

    def add_assistant_message(self, content: str) -> None:
        self.messages.append({"role": "assistant", "content": content})

    def add_tool_result(self, result: ToolResult) -> None:
        self.tool_results.append(result)
        self.messages.append(
            {
                "role": "tool",
                "content": result.raw_result,
                "result_id": result.result_id,
                "tool_name": result.tool_name,
            }
        )

    def build_messages(self, stage: str = "planning", selected_tools: list[str] | None = None) -> list[dict[str, str]]:
        full_tool_docs: list[str] = []
        for spec in self.tool_registry.available_tools():
            skill = self.tool_registry.load_full_skill(spec.name)
            full_tool_docs.append(f"## {spec.name}\n{skill}")
        tool_text = "\n\n".join(full_tool_docs)
        history = "\n".join(f"{msg['role']}: {msg['content']}" for msg in self.messages)
        prompt = "\n\n".join([self.system_prompt, "[完整工具说明]", tool_text, "[完整历史]", history])
        self.loaded_skill_names = [spec.name for spec in self.tool_registry.available_tools()]
        self.loaded_skill_tokens = estimate_tokens(tool_text)
        self.last_token_breakdown = {
            "system": estimate_tokens(self.system_prompt),
            "tool_schema": estimate_tokens(tool_text),
            "history": estimate_tokens(history),
            "summary": 0,
            "tool_summary": 0,
            "branch": 0,
            "tool_brief": 0,
            "loaded_skill": self.loaded_skill_tokens,
        }
        return [{"role": "user", "content": prompt}]

    def latest_metrics_hint(self) -> dict:
        raw_tool_tokens = sum(result.raw_token_len for result in self.tool_results)
        return {
            **self.last_token_breakdown,
            "raw_tool_tokens": raw_tool_tokens,
            "injected_tool_tokens": raw_tool_tokens,
            "tool_compression_ratio": 1.0,
            "loaded_skill_names": self.loaded_skill_names,
            "loaded_skill_tokens": self.loaded_skill_tokens,
        }
