from __future__ import annotations

import json

from agentmem.memory.context_compressor import ContextCompressor
from agentmem.memory.display import prompt_display_text, prompt_display_tokens
from agentmem.memory.memory_object import estimate_tokens
from agentmem.memory.tool_result_store import ToolResultStore
from agentmem.tools.registry import ToolRegistry
from agentmem.tools.result import ToolResult


class OptimizedMemory:
    """AgentMem 优化版：稳定前缀、工具 brief、按需 skill、工具结果外置、历史压缩。"""

    mode = "optimized"

    def __init__(
        self,
        system_prompt: str,
        tool_registry: ToolRegistry,
        result_store: ToolResultStore,
        recent_rounds: int = 3,
        enable_tool_externalization: bool = True,
        enable_skill_lazy_loading: bool = True,
        enable_history_summary: bool = True,
    ) -> None:
        self.system_prompt = system_prompt
        self.tool_registry = tool_registry
        self.result_store = result_store
        self.recent_rounds = recent_rounds
        self.enable_tool_externalization = enable_tool_externalization
        self.enable_skill_lazy_loading = enable_skill_lazy_loading
        self.enable_history_summary = enable_history_summary
        self.messages: list[dict] = []
        self.tool_results: list[ToolResult] = []
        self.compressor = ContextCompressor()
        self.last_token_breakdown: dict[str, int] = {}
        self.loaded_skill_names: list[str] = []
        self.loaded_skill_tokens = 0

    def add_user_message(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})

    def add_assistant_message(self, content: str) -> None:
        self.messages.append({"role": "assistant", "content": content})

    def add_tool_result(self, result: ToolResult) -> None:
        self.tool_results.append(result)
        content = self._tool_prompt_record(result)
        self.messages.append(
            {
                "role": "tool",
                "content": content,
                "result_id": result.result_id,
                "tool_name": result.tool_name,
            }
        )

    def build_messages(self, stage: str = "planning", selected_tools: list[str] | None = None) -> list[dict[str, str]]:
        selected_tools = selected_tools or []
        if self.enable_history_summary:
            compression = self.compressor.compress(self.messages, recent_rounds=self.recent_rounds)
            summary = compression.summary
            recent_messages = compression.recent_messages
        else:
            summary = ""
            recent_messages = self.messages
        tool_briefs = json.dumps(self.tool_registry.list_tool_briefs(), ensure_ascii=False, indent=2)

        loaded_skills: list[str] = []
        if self.enable_skill_lazy_loading:
            for name in selected_tools:
                try:
                    loaded_skills.append(f"## {name}\n{self.tool_registry.load_full_skill(name)}")
                except KeyError:
                    continue
        loaded_skill_text = "\n\n".join(loaded_skills)
        self.loaded_skill_names = selected_tools if self.enable_skill_lazy_loading else []
        self.loaded_skill_tokens = estimate_tokens(loaded_skill_text)

        recent_dialogue = "\n".join(f"{m['role']}: {m['content']}" for m in recent_messages)
        tool_summaries = "\n".join(self._tool_prompt_record(result) for result in self.tool_results[-8:])
        project_rules = "固定说明：保持 system/project/tool brief 前缀稳定；长工具结果使用 result_id 按需引用。"
        prompt = "\n\n".join(
            [
                f"[system]\n{self.system_prompt}",
                f"[project_rules]\n{project_rules}",
                f"[tool_briefs]\n{tool_briefs}",
                f"[loaded_skills]\n{loaded_skill_text}",
                f"[history_summary]\n{summary}",
                f"[recent_dialogue]\n{recent_dialogue}",
                f"[tool_summaries]\n{tool_summaries}",
            ]
        )
        self.last_token_breakdown = {
            "system": estimate_tokens(self.system_prompt) + estimate_tokens(project_rules),
            "tool_schema": estimate_tokens(tool_briefs) + estimate_tokens(loaded_skill_text),
            "history": estimate_tokens(recent_dialogue),
            "summary": estimate_tokens(summary),
            "tool_summary": estimate_tokens(tool_summaries),
            "branch": 0,
            "tool_brief": estimate_tokens(tool_briefs),
            "loaded_skill": estimate_tokens(loaded_skill_text),
        }
        return [{"role": "user", "content": prompt}]

    def latest_metrics_hint(self) -> dict:
        raw_tool_tokens = sum(result.raw_token_len for result in self.tool_results)
        injected = (
            sum(result.summary_token_len for result in self.tool_results)
            if self.enable_tool_externalization
            else sum(prompt_display_tokens(result, estimate_tokens) for result in self.tool_results)
        )
        ratios = [result.compression_ratio for result in self.tool_results if result.raw_token_len > 0]
        return {
            **self.last_token_breakdown,
            "raw_tool_tokens": raw_tool_tokens,
            "injected_tool_tokens": injected,
            "tool_compression_ratio": sum(ratios) / len(ratios) if ratios else 1.0,
            "loaded_skill_names": self.loaded_skill_names,
            "loaded_skill_tokens": self.loaded_skill_tokens,
        }

    def _tool_prompt_record(self, result: ToolResult) -> str:
        if not self.enable_tool_externalization:
            return prompt_display_text(result)
        return "\n".join(
            [
                f"tool_name: {result.tool_name}",
                f"result_id: {result.result_id}",
                f"status: {result.status}",
                f"raw_token_len: {result.raw_token_len}",
                f"summary_token_len: {result.summary_token_len}",
                f"summary: {result.summary}",
            ]
        )
