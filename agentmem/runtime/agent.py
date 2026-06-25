from __future__ import annotations

import time
from uuid import uuid4

from agentmem.event_memory.memory_delta import MemoryDeltaParser
from agentmem.memory.display import prompt_display_tokens
from agentmem.memory.memory_object import estimate_tokens
from agentmem.metrics.gpu_monitor import get_peak_gpu_memory_mb
from agentmem.tools.executor import ToolExecutor
from agentmem.tools.registry import ToolRegistry
from agentmem.tools.router import ToolRouter


class AgentRuntime:
    """轻量 Agent Runtime：用户输入 -> 工具路由/执行 -> 内存构造 -> LLM。"""

    def __init__(
        self,
        memory,
        tools: ToolRegistry,
        llm_client,
        tool_executor: ToolExecutor | None = None,
        tool_router: ToolRouter | None = None,
    ) -> None:
        self.memory = memory
        self.tools = tools
        self.llm_client = llm_client
        self.tool_executor = tool_executor
        self.tool_router = tool_router or ToolRouter()
        self.round = 0
        self.memory_delta_parser = MemoryDeltaParser()

    def run(self, user_input: str, stage: str = "planning") -> tuple[str, dict]:
        self.round += 1
        run_id = _new_run_id()
        if hasattr(self.memory, "start_round"):
            self.memory.start_round(self.round, stage, user_input, run_id=run_id)
        self.memory.add_user_message(user_input)

        decision = self.tool_router.route(user_input, stage, self.tools.available_tools())
        selected_tools = decision.selected_tool_names
        tool_results = []
        if self.tool_executor:
            for tool_name in selected_tools:
                if hasattr(self.memory, "record_tool_call"):
                    self.memory.record_tool_call(tool_name, user_input, stage)
                start = time.perf_counter()
                result = self.tool_executor.execute(tool_name, user_input, context={"stage": stage})
                self.memory.add_tool_result(result)
                tool_results.append(result)
                result.latency = time.perf_counter() - start

        messages = self.memory.build_messages(stage=stage, selected_tools=selected_tools)
        response = self.llm_client.chat(messages)
        parsed = self.memory_delta_parser.parse(response.get("content", ""))
        assistant_response = parsed.assistant_response
        self.memory.add_assistant_message(assistant_response)
        if hasattr(self.memory, "record_memory_delta"):
            self.memory.record_memory_delta(parsed.memory_delta)
        hint = self.memory.latest_metrics_hint()
        round_raw_tool_tokens = sum(result.raw_token_len for result in tool_results)
        uses_tool_externalization = bool(getattr(self.memory, "enable_tool_externalization", False))
        round_injected_tool_tokens = (
            sum(result.summary_token_len for result in tool_results)
            if uses_tool_externalization
            else sum(prompt_display_tokens(result, estimate_tokens) for result in tool_results)
        )
        round_ratios = [result.compression_ratio for result in tool_results if result.raw_token_len > 0]
        round_tool_compression_ratio = (
            (sum(round_ratios) / len(round_ratios) if round_ratios else 1.0)
            if uses_tool_externalization
            else 1.0
        )
        structural_success = bool(assistant_response.strip()) and all(
            result.status not in {"failed", "timeout", "permission_denied"} for result in tool_results
        )

        metrics = {
            "run_id": run_id,
            "round": self.round,
            "mode": self.memory.mode,
            "stage": stage,
            "prompt_tokens": response["prompt_tokens"],
            "system_tokens": hint.get("system", 0),
            "tool_schema_tokens": hint.get("tool_schema", 0),
            "tool_brief_tokens": hint.get("tool_brief", 0),
            "loaded_skill_tokens": hint.get("loaded_skill_tokens", 0),
            "loaded_skill_names": ",".join(hint.get("loaded_skill_names", [])),
            "tool_names": ",".join(result.tool_name for result in tool_results),
            "route_reason": "; ".join(
                f"{name}:{reason}" for name, reason in decision.route_reason.items()
            ),
            "history_tokens": hint.get("history", 0),
            "summary_tokens": hint.get("summary", 0),
            "tool_summary_tokens": hint.get("tool_summary", 0),
            "branch_tokens": hint.get("branch", 0),
            "raw_tool_tokens": round_raw_tool_tokens,
            "injected_tool_tokens": round_injected_tool_tokens,
            "tool_compression_ratio": round_tool_compression_ratio,
            "latency": response["latency"] + sum(result.latency for result in tool_results),
            "ttft": response.get("ttft", -1),
            "output_tokens": response["completion_tokens"],
            "total_tokens": response["total_tokens"],
            "tokens_per_second": response.get("tokens_per_second", -1),
            "peak_gpu_memory_mb": get_peak_gpu_memory_mb(),
            "success": structural_success,
        }
        if hasattr(self.memory, "record_metrics"):
            self.memory.record_metrics(metrics)
            final_hint = self.memory.latest_metrics_hint()
            for key in [
                "full_history_tokens",
                "state_view_tokens",
                "event_count",
                "memory_delta_count",
                "fact_count",
                "decision_count",
                "artifact_ref_count",
                "snapshot_count",
                "memory_run_id",
            ]:
                if key in final_hint:
                    metrics[key] = final_hint[key]
        return assistant_response, metrics


def _new_run_id() -> str:
    return f"run_{int(time.time() * 1000)}_{uuid4().hex[:8]}"
