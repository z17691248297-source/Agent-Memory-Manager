from __future__ import annotations

import time
from uuid import uuid4

from agentmem.event_memory.memory_delta import MemoryDelta, MemoryDeltaParser
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
        memory_delta_extractor=None,
        max_steps: int = 1,
        enable_next_action_loop: bool = False,
    ) -> None:
        self.memory = memory
        self.tools = tools
        self.llm_client = llm_client
        self.tool_executor = tool_executor
        self.tool_router = tool_router or ToolRouter()
        self.round = 0
        self.memory_delta_parser = MemoryDeltaParser()
        self.memory_delta_extractor = memory_delta_extractor
        self.max_steps = max(1, int(max_steps or 1))
        self.enable_next_action_loop = bool(enable_next_action_loop)

    def run(self, user_input: str, stage: str = "planning", tool_context: dict | None = None) -> tuple[str, dict]:
        self.round += 1
        tool_context = dict(tool_context or {})
        run_id = _new_run_id()
        if hasattr(self.memory, "start_round"):
            self.memory.start_round(self.round, stage, user_input, run_id=run_id)
        if hasattr(self.memory, "set_task_requirements"):
            self.memory.set_task_requirements(
                required_facts=tool_context.get("required_facts") or [],
                required_answer_points=tool_context.get("required_answer_points") or [],
            )
        self.memory.add_user_message(user_input)

        decision = self.tool_router.route(user_input, stage, self.tools.available_tools())
        selected_tools = list(decision.selected_tool_names)
        tool_results = []
        prompt_tokens = output_tokens = total_tokens = 0
        latency = ttft = tokens_per_second = 0.0
        assistant_response = ""
        completion_reached = False
        llm_error = ""
        extractor_error = ""
        extractor_calls = 0
        extractor_success_count = 0
        extractor_failure_count = 0
        step_index = 0

        def apply_extractor(assistant_text: str) -> None:
            nonlocal extractor_calls, extractor_error, extractor_success_count, extractor_failure_count
            memory_delta = self._extract_memory_delta(user_input, stage, assistant_text)
            if self.memory_delta_extractor is None:
                return
            extractor_calls += 1
            call_error = str(getattr(self.memory_delta_extractor, "last_error", "") or "")
            if call_error:
                extractor_error = call_error
            if memory_delta.is_empty() or call_error:
                extractor_failure_count += 1
                return
            extractor_success_count += 1
            if hasattr(self.memory, "record_memory_delta"):
                self.memory.record_memory_delta(memory_delta)

        if self.tool_executor and selected_tools and not self.enable_next_action_loop:
            for tool_name in selected_tools:
                result = self._execute_tool(tool_name, user_input, stage, tool_results, tool_context)
                if result.status in {"failed", "timeout", "permission_denied"}:
                    completion_reached = True
                    break

        max_llm_steps = self.max_steps if self.enable_next_action_loop else 1
        for step_index in range(1, max_llm_steps + 1):
            messages = self.memory.build_messages(stage=stage, selected_tools=selected_tools)
            try:
                response = self.llm_client.chat(messages)
            except RuntimeError as exc:
                llm_error = str(exc)
                prompt_tokens += estimate_tokens(str(messages))
                assistant_response = f"LLM call failed: {llm_error}"
                self.memory.add_assistant_message(assistant_response)
                completion_reached = True
                break
            prompt_tokens += int(response.get("prompt_tokens", 0) or 0)
            output_tokens += int(response.get("completion_tokens", 0) or 0)
            total_tokens += int(response.get("total_tokens", 0) or 0)
            latency += float(response.get("latency", 0.0) or 0.0)
            if step_index == 1:
                ttft = float(response.get("ttft", -1) or -1)
            tokens_per_second = float(response.get("tokens_per_second", -1) or -1)

            parsed = self.memory_delta_parser.parse(response.get("content", ""))
            assistant_response = parsed.assistant_response
            next_action = parsed.next_action or {}

            force_tool_after_draft = (
                self.enable_next_action_loop
                and stage == "tool_calling"
                and step_index == 1
                and selected_tools
                and not tool_results
                and _is_final_action(next_action)
            )
            if force_tool_after_draft:
                result = self._execute_tool(selected_tools[0], user_input, stage, tool_results, tool_context)
                if result.status not in {"failed", "timeout", "permission_denied"}:
                    apply_extractor("")
                    continue
                completion_reached = True
                break

            self.memory.add_assistant_message(assistant_response)
            memory_delta = parsed.memory_delta
            if memory_delta.is_empty():
                should_extract = not (
                    self.enable_next_action_loop
                    and stage == "tool_calling"
                    and selected_tools
                    and not tool_results
                )
                if should_extract:
                    apply_extractor(assistant_response)
            elif hasattr(self.memory, "record_memory_delta"):
                self.memory.record_memory_delta(memory_delta)

            if not self.enable_next_action_loop or _is_final_action(next_action):
                completion_reached = True
                break
            if str(next_action.get("type", "")).lower() != "tool_call":
                completion_reached = True
                break
            tool_name = str(next_action.get("tool") or next_action.get("name") or "")
            if not tool_name:
                completion_reached = True
                break
            result = self._execute_tool(tool_name, _tool_input_from_action(next_action, user_input), stage, tool_results, tool_context)
            selected_tools = [tool_name]
            if result.status in {"failed", "timeout", "permission_denied"}:
                self.memory.add_assistant_message(f"Tool call failed: {tool_name} status={result.status}")
                if hasattr(self.memory, "record_memory_delta"):
                    self.memory.record_memory_delta(
                        MemoryDelta(
                            warnings=[
                                f"Tool call failed: {tool_name} status={result.status} error={result.error or ''}".strip()
                            ]
                        )
                    )
                completion_reached = True
                break
            apply_extractor("")

        if not completion_reached and assistant_response:
            self.memory.add_assistant_message("Max agent steps reached; returning latest assistant response.")
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
        structural_success = bool(assistant_response.strip()) and not llm_error and all(
            result.status not in {"failed", "timeout", "permission_denied"} for result in tool_results
        )

        metrics = {
            "run_id": run_id,
            "round": self.round,
            "mode": self.memory.mode,
            "stage": stage,
            "model": getattr(self.llm_client, "model", ""),
            "prompt_tokens": prompt_tokens,
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
            "latency": latency + sum(result.latency for result in tool_results),
            "ttft": ttft,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens or (prompt_tokens + output_tokens),
            "tokens_per_second": tokens_per_second,
            "peak_gpu_memory_mb": get_peak_gpu_memory_mb(),
            "success": structural_success,
            "agent_steps": max_llm_steps if not completion_reached else min(max_llm_steps, step_index),
            "llm_error": llm_error,
            "extractor_calls": extractor_calls,
            "extractor_error": extractor_error,
            "extractor_success_count": extractor_success_count,
            "extractor_failure_count": extractor_failure_count,
            "extractor_effective": bool(extractor_success_count > 0),
            "extractor_status": "active" if extractor_success_count > 0 else ("fallback" if extractor_calls else "not_used"),
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

    def _extract_memory_delta(self, user_input: str, stage: str, assistant_response: str) -> MemoryDelta:
        if self.memory_delta_extractor is None or not hasattr(self.memory, "build_extractor_payload"):
            return MemoryDelta()
        payload = self.memory.build_extractor_payload(
            current_query=user_input,
            stage=stage,
            assistant_response=assistant_response,
        )
        return self.memory_delta_extractor.extract_memory_delta(payload)

    def _execute_tool(self, tool_name: str, input_text: str, stage: str, tool_results: list, tool_context: dict | None = None) -> object:
        if hasattr(self.memory, "record_tool_call"):
            self.memory.record_tool_call(tool_name, input_text, stage)
        start = time.perf_counter()
        context = {"stage": stage, **dict(tool_context or {})}
        result = self.tool_executor.execute(tool_name, input_text, context=context) if self.tool_executor else None
        if result is None:
            raise RuntimeError("tool_executor is not configured")
        self.memory.add_tool_result(result)
        tool_results.append(result)
        result.latency = time.perf_counter() - start
        return result


def _is_final_action(action: dict) -> bool:
    if not action:
        return True
    return str(action.get("type", "")).lower() in {"", "final", "finish", "none"}


def _tool_input_from_action(action: dict, fallback: str) -> str:
    args = action.get("args")
    if isinstance(args, dict):
        for key in ["input", "query", "text", "expression", "path"]:
            value = args.get(key)
            if value not in {None, ""}:
                return str(value)
        return str(args) if args else fallback
    if args not in {None, ""}:
        return str(args)
    return fallback


def _new_run_id() -> str:
    return f"run_{int(time.time() * 1000)}_{uuid4().hex[:8]}"
